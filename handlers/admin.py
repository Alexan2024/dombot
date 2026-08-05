"""Admin control panel (buttons instead of remembering commands).

- /admin  -> inline panel: events, FAQ editor, menu (PDF), contacts/hours,
             booking-intake toggle + its "closed" message, broadcast, statistics.
- Events:  reuses the AddEvent FSM (events.py, lazy-imported to avoid an import
           cycle) and the evt:del: / evt:edit: callbacks from events.py.
- Menu:    admin uploads a PDF once; its Telegram file_id is stored in `settings`
           and re-sent to guests who tap the "Menu" button.
- FAQ:     add / edit / delete bilingual questions (stored in the `faq` table).
- Contacts/hours: editable values stored in `settings` (fallback to config).
- Toggle:  booking intake on/off (settings key 'bookings_enabled'), plus an
           editable RU/EN message shown to guests while intake is off
           (settings keys 'msg_bookings_closed_ru' / '..._en', fallback texts.py).

Broadcast (bc:*) and statistics (stats:*) live in their own routers.
Admin UI is Russian-only, matching the rest of the manager-facing side.
"""
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
    BOOKINGS_CLOSED_KEYS,
    default_bookings_closed,
    esc,
    get_bookings_closed_text,
    get_content,
    is_admin,
    is_bookings_enabled,
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
        [InlineKeyboardButton(
            text="✉️ Текст при закрытых бронях", callback_data="adm:closedmsg"
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


# ---------- message shown while booking intake is off ----------
class EditClosedMsg(StatesGroup):
    waiting_value = State()


_CLOSED_LANG_LABEL = {"ru": "🇷🇺 Русский", "en": "🇬🇧 English"}


async def _closedmsg_view():
    lines = [
        "✉️ <b>Сообщение при закрытом приёме броней</b>",
        "",
        "Гость видит этот текст, когда приём броней выключен.",
        "",
    ]
    rows = []
    for lang in ("ru", "en"):
        value = await get_bookings_closed_text(lang)
        lines.append(f"<b>{_CLOSED_LANG_LABEL[lang]}:</b>\n{esc(value)}\n")
        rows.append([InlineKeyboardButton(
            text=f"✏️ {_CLOSED_LANG_LABEL[lang]}",
            callback_data=f"adm:closedmsg:{lang}",
        )])
    rows.append([InlineKeyboardButton(
        text="↩️ Вернуть тексты по умолчанию", callback_data="adm:closedmsg:reset"
    )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:panel")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:closedmsg")
async def adm_closedmsg(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    text, kb = await _closedmsg_view()
    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "adm:closedmsg:reset")
async def adm_closedmsg_reset(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    for lang, key in BOOKINGS_CLOSED_KEYS.items():
        await db.set_setting(key, default_bookings_closed(lang))
    await callback.answer("Тексты возвращены к исходным")
    text, kb = await _closedmsg_view()
    await callback.message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("adm:closedmsg:"))
async def adm_closedmsg_pick(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    lang = callback.data.split(":")[2]
    if lang not in BOOKINGS_CLOSED_KEYS:
        await callback.answer()
        return
    current = await get_bookings_closed_text(lang)
    await state.set_state(EditClosedMsg.waiting_value)
    await state.update_data(closed_lang=lang)
    await callback.message.answer(
        f"Текущий текст — {_CLOSED_LANG_LABEL[lang]}:\n{esc(current)}\n\n"
        "Пришлите новый текст одним сообщением. "
        "Форматирование (жирный, курсив, ссылки) сохранится.\n"
        "Для отмены — /cancel."
    )
    await callback.answer()


@router.message(EditClosedMsg.waiting_value, Command("cancel"))
async def closedmsg_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено. Текст не изменился.")


@router.message(EditClosedMsg.waiting_value, F.text)
async def closedmsg_save(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("closed_lang")
    if lang not in BOOKINGS_CLOSED_KEYS:
        await state.clear()
        return
    # html_text keeps the admin's Telegram formatting (bot sends with parse_mode=HTML)
    await db.set_setting(BOOKINGS_CLOSED_KEYS[lang], message.html_text.strip())
    await state.clear()
    await message.answer(f"✅ Текст обновлён — {_CLOSED_LANG_LABEL[lang]}.")
    text, kb = await _closedmsg_view()
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
