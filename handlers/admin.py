"""Admin control panel (buttons instead of remembering commands).

- /admin  -> inline panel: events, FAQ editor, menu (PDF), contacts/hours,
             booking-intake toggle, closed dates, booking hours, the editable
             "unavailable" texts, broadcast, statistics.
- Events:  reuses the AddEvent FSM (events.py, lazy-imported to avoid an import
           cycle) and the evt:del: / evt:edit: callbacks from events.py.
- Menu:    admin uploads a PDF once; its Telegram file_id is stored in `settings`
           and re-sent to guests who tap the "Menu" button.
- FAQ:     add / edit / delete bilingual questions (stored in the `faq` table).
- Contacts/hours: editable values stored in `settings` (fallback to config).
- Toggle:  booking intake on/off (settings key 'bookings_enabled').
- Dates:   close booking for a specific day (`blocked_dates`), with an optional
           per-date message; otherwise the general "date closed" text is used.
- Hours:   one or more bookable windows per weekday (`booking_windows`, minutes
           from midnight). A weekday with no windows at all is a day off.
- Texts:   every guest-facing "unavailable" message is editable per language
           (settings keys msg_{name}_{lang}, fallbacks in texts.py).

Broadcast (bc:*) and statistics (stats:*) live in their own routers.
Admin UI is Russian-only, matching the rest of the manager-facing side.
"""
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config
import database as db
from handlers.common import (
    EDITABLE_MESSAGES,
    LANGS,
    WEEKDAYS_RU,
    default_message,
    esc,
    fmt_date,
    fmt_time,
    get_content,
    get_message,
    is_admin,
    is_bookings_enabled,
    message_key,
    parse_date,
    parse_time,
    window_label,
    windows_label,
)

router = Router()

MENU_FILE_KEY = "menu_file_id"


class SetMenu(StatesGroup):
    waiting_file = State()


# ---------- panel ----------
def _panel_kb(bookings_enabled: bool) -> InlineKeyboardMarkup:
    toggle_text = (
        "🔔 Приём броней: ВКЛ" if bookings_enabled else "🔕 Приём броней: ВЫКЛ"
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎭 События", callback_data="adm:events")],
        [InlineKeyboardButton(text="❓ FAQ (вопросы гостей)", callback_data="adm:faq")],
        [InlineKeyboardButton(text="📎 Обновить меню (PDF)", callback_data="adm:menu")],
        [InlineKeyboardButton(text="📍 Контакты и часы", callback_data="adm:contacts")],
        [InlineKeyboardButton(text=toggle_text, callback_data="adm:toggle")],
        [InlineKeyboardButton(text="📅 Закрытые даты", callback_data="adm:dates")],
        [InlineKeyboardButton(text="🕐 Часы бронирования", callback_data="adm:hours")],
        [InlineKeyboardButton(
            text="✉️ Текст при закрытых бронях",
            callback_data="admmsg:view:bookings_closed",
        )],
        [InlineKeyboardButton(text="📣 Рассылка", callback_data="bc:start")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats:open")],
    ])


@router.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    enabled = await is_bookings_enabled()
    await message.answer("⚙️ <b>Панель администратора</b>", reply_markup=_panel_kb(enabled))


@router.callback_query(F.data == "adm:panel")
async def adm_panel_cb(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    enabled = await is_bookings_enabled()
    await callback.message.answer(
        "⚙️ <b>Панель администратора</b>", reply_markup=_panel_kb(enabled)
    )
    await callback.answer()


# ---------- booking-intake toggle ----------
@router.callback_query(F.data == "adm:toggle")
async def adm_toggle(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    new_state = not await is_bookings_enabled()
    await db.set_setting("bookings_enabled", "1" if new_state else "0")
    try:
        await callback.message.edit_reply_markup(reply_markup=_panel_kb(new_state))
    except Exception:
        pass
    await callback.answer(
        "Приём броней включён ✅" if new_state else "Приём броней выключен ⛔"
    )


# ---------- editable guest-facing messages ----------
class EditMessage(StatesGroup):
    waiting_value = State()


_MSG_TITLE = {
    "bookings_closed": "✉️ Текст при закрытом приёме броней",
    "date_closed": "✉️ Текст при закрытой дате",
    "time_closed": "✉️ Текст при недоступном времени",
}
_MSG_INTRO = {
    "bookings_closed": "Гость видит этот текст, когда приём броней выключен целиком.",
    "date_closed": (
        "Гость видит этот текст, когда выбирает закрытую дату — если для самой "
        "даты не задано отдельное сообщение.\n"
        "Можно использовать <code>{date}</code> — подставится выбранная дата."
    ),
    "time_closed": (
        "Гость видит этот текст, когда указывает время вне доступных часов.\n"
        "Можно использовать <code>{hours}</code> — подставятся все доступные "
        "промежутки выбранного дня (например, «16:00–17:00, 19:00–20:00»).\n"
        "<code>{from}</code> и <code>{to}</code> тоже работают — это начало "
        "первого и конец последнего промежутка."
    ),
}
_MSG_BACK = {
    "bookings_closed": "adm:panel",
    "date_closed": "adm:dates",
    "time_closed": "adm:hours",
}
_LANG_LABEL = {"ru": "🇷🇺 Русский", "en": "🇬🇧 English"}


async def _message_view(name: str):
    lines = [f"<b>{_MSG_TITLE[name]}</b>", "", _MSG_INTRO[name], ""]
    rows = []
    for lang in LANGS:
        value = await get_message(name, lang)
        lines.append(f"<b>{_LANG_LABEL[lang]}:</b>\n{esc(value)}\n")
        rows.append([InlineKeyboardButton(
            text=f"✏️ {_LANG_LABEL[lang]}",
            callback_data=f"admmsg:edit:{name}:{lang}",
        )])
    rows.append([InlineKeyboardButton(
        text="↩️ Вернуть текст по умолчанию", callback_data=f"admmsg:reset:{name}"
    )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=_MSG_BACK[name])])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("admmsg:view:"))
async def admmsg_view(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    name = callback.data.split(":")[2]
    if name not in EDITABLE_MESSAGES:
        await callback.answer()
        return
    text, kb = await _message_view(name)
    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("admmsg:reset:"))
async def admmsg_reset(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    name = callback.data.split(":")[2]
    if name not in EDITABLE_MESSAGES:
        await callback.answer()
        return
    await state.clear()
    for lang in LANGS:
        await db.set_setting(message_key(name, lang), default_message(name, lang))
    await callback.answer("Текст возвращён к исходному")
    text, kb = await _message_view(name)
    await callback.message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("admmsg:edit:"))
async def admmsg_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    parts = callback.data.split(":")  # admmsg edit {name} {lang}
    name, lang = parts[2], parts[3]
    if name not in EDITABLE_MESSAGES or lang not in LANGS:
        await callback.answer()
        return
    current = await get_message(name, lang)
    await state.set_state(EditMessage.waiting_value)
    await state.update_data(msg_name=name, msg_lang=lang)
    await callback.message.answer(
        f"Текущий текст — {_LANG_LABEL[lang]}:\n{esc(current)}\n\n"
        "Пришлите новый текст одним сообщением. "
        "Форматирование (жирный, курсив, ссылки) сохранится.\n"
        "Для отмены — /cancel."
    )
    await callback.answer()


@router.message(EditMessage.waiting_value, Command("cancel"))
async def admmsg_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено. Текст не изменился.")


@router.message(EditMessage.waiting_value, F.text)
async def admmsg_save(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    name, lang = data.get("msg_name"), data.get("msg_lang")
    if name not in EDITABLE_MESSAGES or lang not in LANGS:
        await state.clear()
        return
    # html_text keeps the admin's Telegram formatting (bot sends with parse_mode=HTML)
    await db.set_setting(message_key(name, lang), message.html_text.strip())
    await state.clear()
    await message.answer(f"✅ Текст обновлён — {_LANG_LABEL[lang]}.")
    text, kb = await _message_view(name)
    await message.answer(text, reply_markup=kb)


# ---------- blocked dates ----------
class AddBlockedDate(StatesGroup):
    day = State()
    msg_ru = State()
    msg_en = State()


_SKIP = ("-", "—", "–")


async def _dates_view():
    await db.purge_past_blocked_dates()
    days = await db.list_blocked_dates()
    lines = [
        "📅 <b>Закрытые даты</b>",
        "",
        "На эти даты бот не принимает брони.",
        "",
    ]
    rows = []
    if days:
        for row in days:
            own = "✉️" if (row["message_ru"] or row["message_en"]) else ""
            lines.append(f"• {fmt_date(row['day'])} {own}".strip())
            rows.append([InlineKeyboardButton(
                text=f"🗑 {fmt_date(row['day'])}",
                callback_data=f"admdate:del:{row['day'].isoformat()}",
            )])
        lines.append("")
        lines.append("<i>✉️ — для даты задано своё сообщение.</i>")
    else:
        lines.append("Закрытых дат нет.")
    rows.append([InlineKeyboardButton(text="➕ Закрыть дату", callback_data="admdate:add")])
    rows.append([InlineKeyboardButton(
        text="✉️ Общий текст", callback_data="admmsg:view:date_closed"
    )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:panel")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:dates")
async def adm_dates(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    text, kb = await _dates_view()
    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "admdate:add")
async def admdate_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AddBlockedDate.day)
    await callback.message.answer(
        "Какую дату закрыть? Формат ДД.ММ.ГГГГ — например, 15.08.2026.\n"
        "Для отмены — /cancel."
    )
    await callback.answer()


@router.message(AddBlockedDate.day, Command("cancel"))
@router.message(AddBlockedDate.msg_ru, Command("cancel"))
@router.message(AddBlockedDate.msg_en, Command("cancel"))
async def admdate_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено. Дата не закрыта.")


@router.message(AddBlockedDate.day, F.text)
async def admdate_day(message: Message, state: FSMContext) -> None:
    day = parse_date(message.text)
    if not day:
        await message.answer("Не понял дату. Пример: 15.08.2026")
        return
    await state.update_data(block_day=day.isoformat())
    await state.set_state(AddBlockedDate.msg_ru)
    await message.answer(
        f"Дата: <b>{fmt_date(day)}</b>\n\n"
        "Своё сообщение для этой даты на русском? "
        "Отправьте «-», чтобы использовать общий текст."
    )


@router.message(AddBlockedDate.msg_ru, F.text)
async def admdate_msg_ru(message: Message, state: FSMContext) -> None:
    value = message.html_text.strip()
    if value in _SKIP:
        data = await state.get_data()
        day = datetime.fromisoformat(data["block_day"]).date()
        await db.add_blocked_date(day, None, None)
        await state.clear()
        await message.answer(
            f"✅ {fmt_date(day)} закрыта. Гостям уйдёт общий текст."
        )
        text, kb = await _dates_view()
        await message.answer(text, reply_markup=kb)
        return
    await state.update_data(block_msg_ru=value)
    await state.set_state(AddBlockedDate.msg_en)
    await message.answer(
        "Тот же текст на английском? "
        "Отправьте «-», чтобы англоязычные гости получили общий текст."
    )


@router.message(AddBlockedDate.msg_en, F.text)
async def admdate_msg_en(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    day = datetime.fromisoformat(data["block_day"]).date()
    value = message.html_text.strip()
    msg_en = None if value in _SKIP else value
    await db.add_blocked_date(day, data.get("block_msg_ru"), msg_en)
    await state.clear()
    await message.answer(f"✅ {fmt_date(day)} закрыта.")
    text, kb = await _dates_view()
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("admdate:del:"))
async def admdate_del(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    day = datetime.fromisoformat(callback.data.split(":", 2)[2]).date()
    await db.delete_blocked_date(day)
    await callback.answer("Дата снова открыта")
    text, kb = await _dates_view()
    await callback.message.answer(text, reply_markup=kb)


# ---------- booking hours (several windows per weekday) ----------
class AddHours(StatesGroup):
    waiting_value = State()


_DAY_OFF_WORDS = ("выходной", "закрыто", "закрыт", "нет", "off", "closed")
_WINDOW_SEPARATORS = (",", ";", "\n")


def _parse_window(text: str):
    """'12:00-23:00' -> (open_min, close_min); None if unparseable."""
    raw = text.strip().lower().replace("до", "-")
    for sep in ("—", "–", "..", "-"):
        raw = raw.replace(sep, "-")
    parts = [p.strip() for p in raw.split("-") if p.strip()]
    if len(parts) != 2:
        return None
    start = parse_time(parts[0])
    end = parse_time(parts[1])
    if start is None or end is None or start == end:
        return None
    return start, end


def _parse_windows(text: str):
    """Parse one or several windows: '16:00-17:00, 19:00-20:00'.

    Returns (windows, bad_chunk). `bad_chunk` is the first unparseable piece,
    in which case `windows` is empty.
    """
    raw = text
    for sep in _WINDOW_SEPARATORS:
        raw = raw.replace(sep, "|")
    windows = []
    for chunk in (c.strip() for c in raw.split("|")):
        if not chunk:
            continue
        window = _parse_window(chunk)
        if window is None:
            return [], chunk
        windows.append(window)
    return windows, None


def _short(text: str, limit: int = 34) -> str:
    return text if len(text) <= limit else text[:limit - 1] + "…"


async def _day_windows(weekday: int) -> list[tuple[int, int]]:
    rows = await db.list_day_windows(weekday)
    return [(int(r["open_min"]), int(r["close_min"])) for r in rows]


async def _hours_view():
    rows_db = await db.list_booking_windows()
    by_day: dict[int, list[tuple[int, int]]] = {}
    for row in rows_db:
        by_day.setdefault(int(row["weekday"]), []).append(
            (int(row["open_min"]), int(row["close_min"]))
        )

    lines = [
        "🕐 <b>Часы бронирования</b>",
        "",
        "В эти часы гость может забронировать стол. "
        "В одном дне можно задать несколько промежутков — например, "
        "16:00–17:00 и 19:00–20:00.",
        "",
    ]
    rows = []
    for day in range(7):
        windows = by_day.get(day, [])
        label = windows_label(windows) if windows else "выходной"
        lines.append(f"<b>{WEEKDAYS_RU[day]}:</b> {label}")
        rows.append([InlineKeyboardButton(
            text=_short(f"✏️ {WEEKDAYS_RU[day]} · {label}"),
            callback_data=f"admhours:day:{day}",
        )])
    rows.append([InlineKeyboardButton(
        text="✉️ Текст при недоступном времени", callback_data="admmsg:view:time_closed"
    )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:panel")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def _day_view(weekday: int):
    """One weekday: its windows, with a delete button per window."""
    rows_db = await db.list_day_windows(weekday)
    lines = [f"🕐 <b>{WEEKDAYS_RU[weekday]}</b>", ""]
    rows = []
    if rows_db:
        lines.append("Доступные промежутки:")
        for row in rows_db:
            label = window_label(int(row["open_min"]), int(row["close_min"]))
            lines.append(f"• {label}")
            rows.append([InlineKeyboardButton(
                text=f"🗑 {label}", callback_data=f"admhours:del:{row['id']}"
            )])
    else:
        lines.append("Сейчас это <b>выходной</b> — брони не принимаются.")
    lines.append("")
    lines.append("<i>Промежутков может быть сколько угодно. Гость получит "
                 "кнопки со временем из всех промежутков.</i>")

    rows.append([InlineKeyboardButton(
        text="➕ Добавить промежуток", callback_data=f"admhours:add:{weekday}"
    )])
    if rows_db:
        rows.append([InlineKeyboardButton(
            text="🚫 Сделать выходным", callback_data=f"admhours:off:{weekday}"
        )])
    rows.append([InlineKeyboardButton(text="⬅️ К дням недели", callback_data="adm:hours")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:hours")
async def adm_hours(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    text, kb = await _hours_view()
    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("admhours:day:"))
async def admhours_day(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    day = int(callback.data.split(":")[2])
    if day not in range(7):
        await callback.answer()
        return
    await state.clear()
    text, kb = await _day_view(day)
    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("admhours:add:"))
async def admhours_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    day = int(callback.data.split(":")[2])
    if day not in range(7):
        await callback.answer()
        return
    current = await _day_windows(day)
    now_label = windows_label(current) if current else "выходной"
    await state.set_state(AddHours.waiting_value)
    await state.update_data(hours_day=day)
    await callback.message.answer(
        f"<b>{WEEKDAYS_RU[day]}</b> — сейчас: {now_label}\n\n"
        "Пришлите промежуток в формате <code>19:00-20:00</code>.\n"
        "Можно сразу несколько через запятую: "
        "<code>16:00-17:00, 19:00-20:00</code>.\n"
        "Промежуток через полночь тоже работает: <code>22:00-01:00</code>.\n\n"
        "Слово <b>выходной</b> уберёт все промежутки этого дня.\n"
        "Для отмены — /cancel."
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admhours:del:"))
async def admhours_del(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    window_id = int(callback.data.split(":")[2])
    row = await db.get_booking_window(window_id)
    if not row:
        await callback.answer("Промежуток не найден", show_alert=True)
        return
    day = int(row["weekday"])
    await db.delete_booking_window(window_id)
    await callback.answer("Промежуток удалён")
    text, kb = await _day_view(day)
    await callback.message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("admhours:off:"))
async def admhours_off(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    day = int(callback.data.split(":")[2])
    if day not in range(7):
        await callback.answer()
        return
    await state.clear()
    await db.clear_day_windows(day)
    await callback.answer(f"{WEEKDAYS_RU[day]} — выходной")
    text, kb = await _day_view(day)
    await callback.message.answer(text, reply_markup=kb)


@router.message(AddHours.waiting_value, Command("cancel"))
async def admhours_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено. Часы не изменились.")


@router.message(AddHours.waiting_value, F.text)
async def admhours_save(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    day = data.get("hours_day")
    if day not in range(7):
        await state.clear()
        return

    raw = message.text.strip().lower()
    if raw in _DAY_OFF_WORDS:
        await db.clear_day_windows(day)
        await state.clear()
        await message.answer(f"✅ {WEEKDAYS_RU[day]} — выходной, брони не принимаются.")
        text, kb = await _day_view(day)
        await message.answer(text, reply_markup=kb)
        return

    windows, bad = _parse_windows(message.text)
    if bad is not None or not windows:
        hint = f"Не понял «{esc(bad)}». " if bad else "Не понял. "
        await message.answer(
            hint
            + "Пример: <code>19:00-20:00</code> или "
              "<code>16:00-17:00, 19:00-20:00</code>.\n"
              "Слово <b>выходной</b> уберёт все промежутки дня."
        )
        return

    added, skipped = 0, 0
    for open_min, close_min in windows:
        window_id = await db.add_booking_window(day, open_min, close_min)
        if window_id is None:
            skipped += 1
        else:
            added += 1

    await state.clear()
    parts = []
    if added:
        parts.append(f"добавлено: {added}")
    if skipped:
        parts.append(f"уже были: {skipped}")
    current = await _day_windows(day)
    await message.answer(
        f"✅ {WEEKDAYS_RU[day]} — {', '.join(parts)}.\n"
        f"Итого: {windows_label(current) if current else 'выходной'}."
    )
    text, kb = await _day_view(day)
    await message.answer(text, reply_markup=kb)


# ---------- events: view / add / edit / delete ----------
async def _events_list_kb():
    """Admin events list: text + keyboard (edit/delete per event + add)."""
    events = await db.list_upcoming_events()
    if not events:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить событие", callback_data="adm:addevent")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:panel")],
        ])
        return "Ближайших событий нет.", kb

    lines = ["<b>Ближайшие события:</b>", ""]
    rows = []
    for e in events:
        d = e["event_date"].strftime("%d.%m.%Y")
        lines.append(f"№{e['id']} · {d} · {esc(e['title'])}")
        rows.append([
            InlineKeyboardButton(text=f"✏️ №{e['id']}", callback_data=f"evt:edit:{e['id']}"),
            InlineKeyboardButton(text=f"🗑 №{e['id']}", callback_data=f"evt:del:{e['id']}"),
        ])
    rows.append([InlineKeyboardButton(text="➕ Добавить событие", callback_data="adm:addevent")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:panel")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:events")
async def adm_events(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    text, kb = await _events_list_kb()
    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "adm:addevent")
async def adm_addevent(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    # lazy import avoids a handlers package import cycle (admin <-> events)
    from handlers.events import AddEvent
    await state.set_state(AddEvent.date)
    await callback.message.answer("Дата события? (в формате ДД.ММ.ГГГГ или ГГГГ-ММ-ДД)")
    await callback.answer()


# ---------- menu: update PDF ----------
@router.callback_query(F.data == "adm:menu")
async def adm_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(SetMenu.waiting_file)
    await callback.message.answer(
        "📎 Пришлите PDF-файл с меню одним сообщением (как документ).\n"
        "Он заменит текущее меню, которое видят гости по кнопке «Меню».\n\n"
        "Для отмены — /cancel."
    )
    await callback.answer()


@router.message(SetMenu.waiting_file, Command("cancel"))
async def setmenu_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено. Меню осталось прежним.")


@router.message(SetMenu.waiting_file, F.document)
async def setmenu_file(message: Message, state: FSMContext) -> None:
    doc = message.document
    is_pdf = (
        doc.mime_type == "application/pdf"
        or (doc.file_name or "").lower().endswith(".pdf")
    )
    if not is_pdf:
        await message.answer("Нужен именно PDF. Пришлите документ в формате PDF или /cancel.")
        return
    await db.set_setting(MENU_FILE_KEY, doc.file_id)
    await state.clear()
    await message.answer(
        "✅ Меню обновлено. Теперь гости получают этот файл по кнопке «Меню»."
    )


@router.message(SetMenu.waiting_file, F.text)
async def setmenu_wrong(message: Message) -> None:
    await message.answer("Жду PDF-файл (как документ). Или /cancel для отмены.")


# ---------- contacts & hours ----------
# field -> (settings key, config default, label)
_CONTACT_FIELDS = {
    "address": ("info_address", config.ADDRESS, "Адрес"),
    "hours": ("info_hours", config.WORKING_HOURS, "Часы работы"),
    "phone": ("info_phone", config.PHONE, "Телефон"),
    "map": ("info_map_link", config.MAP_LINK, "Ссылка на карту"),
}


class EditContact(StatesGroup):
    waiting_value = State()


async def _contacts_view():
    lines = ["📍 <b>Контакты и часы</b>", "", "Текущие значения:"]
    rows = []
    for field, (key, default, label) in _CONTACT_FIELDS.items():
        value = await get_content(key, default)
        lines.append(f"<b>{label}:</b> {esc(value)}")
        rows.append([InlineKeyboardButton(text=f"✏️ {label}", callback_data=f"adm:contact:{field}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:panel")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:contacts")
async def adm_contacts(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    text, kb = await _contacts_view()
    await callback.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
    await callback.answer()


@router.callback_query(F.data.startswith("adm:contact:"))
async def adm_contact_pick(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    field = callback.data.split(":")[2]
    if field not in _CONTACT_FIELDS:
        await callback.answer()
        return
    key, default, label = _CONTACT_FIELDS[field]
    current = await get_content(key, default)
    await state.set_state(EditContact.waiting_value)
    await state.update_data(contact_field=field)
    await callback.message.answer(
        f"Текущее значение — «{label}»:\n{esc(current)}\n\n"
        "Пришлите новое значение одним сообщением. Для отмены — /cancel."
    )
    await callback.answer()


@router.message(EditContact.waiting_value, Command("cancel"))
async def contact_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено. Значение не изменилось.")


@router.message(EditContact.waiting_value, F.text)
async def contact_save(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field = data.get("contact_field")
    if field not in _CONTACT_FIELDS:
        await state.clear()
        return
    key, _default, label = _CONTACT_FIELDS[field]
    await db.set_setting(key, message.text.strip())
    await state.clear()
    await message.answer(f"✅ «{label}» обновлено.")


# ---------- FAQ editor ----------
class AddFaq(StatesGroup):
    q_ru = State()
    q_en = State()
    a_ru = State()
    a_en = State()


class EditFaq(StatesGroup):
    waiting_value = State()


_FAQ_FIELD_COL = {
    "qru": "question_ru", "qen": "question_en",
    "aru": "answer_ru", "aen": "answer_en",
}
_FAQ_FIELD_LABEL = {
    "qru": "Вопрос (RU)", "qen": "Вопрос (EN)",
    "aru": "Ответ (RU)", "aen": "Ответ (EN)",
}


async def _faq_list_view():
    items = await db.list_faq()
    rows = []
    for e in items:
        title = e["question_ru"]
        if len(title) > 30:
            title = title[:29] + "…"
        rows.append([InlineKeyboardButton(
            text=f"✏️ №{e['id']} · {title}", callback_data=f"admfaq:edit:{e['id']}"
        )])
    rows.append([InlineKeyboardButton(text="➕ Добавить вопрос", callback_data="admfaq:add")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:panel")])
    header = "❓ <b>FAQ</b>\n" + (
        "Выберите вопрос для редактирования или добавьте новый."
        if items else "Пока вопросов нет — добавьте первый."
    )
    return header, InlineKeyboardMarkup(inline_keyboard=rows)


def _faq_item_kb(faq_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Вопрос RU", callback_data=f"admfaq:field:{faq_id}:qru"),
            InlineKeyboardButton(text="✏️ Вопрос EN", callback_data=f"admfaq:field:{faq_id}:qen"),
        ],
        [
            InlineKeyboardButton(text="✏️ Ответ RU", callback_data=f"admfaq:field:{faq_id}:aru"),
            InlineKeyboardButton(text="✏️ Ответ EN", callback_data=f"admfaq:field:{faq_id}:aen"),
        ],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admfaq:del:{faq_id}")],
        [InlineKeyboardButton(text="⬅️ К списку", callback_data="adm:faq")],
    ])


async def _faq_item_view(faq_id: int):
    e = await db.get_faq(faq_id)
    if not e:
        return None, None
    text = (
        f"❓ <b>FAQ №{faq_id}</b>\n\n"
        f"<b>Вопрос (RU):</b> {esc(e['question_ru'])}\n"
        f"<b>Вопрос (EN):</b> {esc(e['question_en'])}\n\n"
        f"<b>Ответ (RU):</b>\n{esc(e['answer_ru'])}\n\n"
        f"<b>Ответ (EN):</b>\n{esc(e['answer_en'])}"
    )
    return text, _faq_item_kb(faq_id)


@router.callback_query(F.data == "adm:faq")
async def adm_faq(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    text, kb = await _faq_list_view()
    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "admfaq:add")
async def admfaq_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AddFaq.q_ru)
    await callback.message.answer(
        "Новый вопрос.\n\nВведите <b>вопрос на русском</b> (или /cancel):"
    )
    await callback.answer()


@router.message(AddFaq.q_ru, Command("cancel"))
@router.message(AddFaq.q_en, Command("cancel"))
@router.message(AddFaq.a_ru, Command("cancel"))
@router.message(AddFaq.a_en, Command("cancel"))
async def addfaq_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено. Вопрос не добавлен.")


@router.message(AddFaq.q_ru, F.text)
async def addfaq_qru(message: Message, state: FSMContext) -> None:
    await state.update_data(q_ru=message.text.strip())
    await state.set_state(AddFaq.q_en)
    await message.answer("Введите <b>вопрос на английском</b>:")


@router.message(AddFaq.q_en, F.text)
async def addfaq_qen(message: Message, state: FSMContext) -> None:
    await state.update_data(q_en=message.text.strip())
    await state.set_state(AddFaq.a_ru)
    await message.answer("Введите <b>ответ на русском</b>:")


@router.message(AddFaq.a_ru, F.text)
async def addfaq_aru(message: Message, state: FSMContext) -> None:
    await state.update_data(a_ru=message.text.strip())
    await state.set_state(AddFaq.a_en)
    await message.answer("Введите <b>ответ на английском</b>:")


@router.message(AddFaq.a_en, F.text)
async def addfaq_aen(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    faq_id = await db.add_faq(
        data["q_ru"], data["q_en"], data["a_ru"], message.text.strip()
    )
    await state.clear()
    await message.answer(f"✅ Вопрос №{faq_id} добавлен.")
    text, kb = await _faq_list_view()
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("admfaq:edit:"))
async def admfaq_edit(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    faq_id = int(callback.data.split(":")[2])
    text, kb = await _faq_item_view(faq_id)
    if not text:
        await callback.answer("Не найдено", show_alert=True)
        return
    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("admfaq:field:"))
async def admfaq_field(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    parts = callback.data.split(":")  # admfaq field {id} {code}
    faq_id = int(parts[2])
    code = parts[3]
    if code not in _FAQ_FIELD_COL:
        await callback.answer()
        return
    await state.set_state(EditFaq.waiting_value)
    await state.update_data(faq_id=faq_id, faq_col=_FAQ_FIELD_COL[code])
    await callback.message.answer(
        f"Пришлите новое значение — «{_FAQ_FIELD_LABEL[code]}». Для отмены — /cancel."
    )
    await callback.answer()


@router.message(EditFaq.waiting_value, Command("cancel"))
async def editfaq_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.")


@router.message(EditFaq.waiting_value, F.text)
async def editfaq_save(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    faq_id = data["faq_id"]
    col = data["faq_col"]
    await db.update_faq_field(faq_id, col, message.text.strip())
    await state.clear()
    await message.answer("✅ Обновлено.")
    text, kb = await _faq_item_view(faq_id)
    if text:
        await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("admfaq:del:"))
async def admfaq_del(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    faq_id = int(callback.data.split(":")[2])
    await db.delete_faq(faq_id)
    await callback.answer("Удалено")
    text, kb = await _faq_list_view()
    await callback.message.answer(text, reply_markup=kb)
