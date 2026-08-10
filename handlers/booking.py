"""Booking conversation (FSM). Collects details and forwards a request to managers."""
import re
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

import config
import database as db
from handlers.common import (
    check_date,
    day_windows,
    esc,
    fill,
    fmt_date,
    fmt_time,
    get_bookings_closed_text,
    get_lang,
    get_message,
    is_bookings_enabled,
    parse_date,
    parse_time,
    sort_windows,
    time_in_windows,
    windows_label,
    windows_slots,
)
from keyboards import (
    confirm_kb,
    date_kb,
    guests_kb,
    main_menu_kb,
    manager_kb,
    phone_kb,
    requests_kb,
    time_kb,
)
from texts import T, t

router = Router()

# Parties of this size or larger are flagged for the managers (deposit + service).
LARGE_PARTY_THRESHOLD = 6


class Booking(StatesGroup):
    date = State()
    time = State()
    guests = State()
    guests_number = State()
    name = State()
    phone = State()
    requests = State()
    confirm = State()


def _label(text: str, key: str) -> bool:
    return text in (T["ru"][key], T["en"][key])


def _cancel_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, "btn_cancel"))]],
        resize_keyboard=True,
    )


def guests_count(text: str) -> int | None:
    """Best-effort numeric guest count from a stored value ('6', '6 человек').
    Returns None when nothing numeric was typed."""
    match = re.search(r"\d+", text or "")
    return int(match.group()) if match else None


def _state_windows(data: dict) -> list[tuple[int, int]]:
    """Windows kept in the FSM. Falls back to the single open/close pair stored
    by older versions of the bot, so a leftover FSM keeps working."""
    raw = data.get("windows")
    if raw:
        return [(int(open_min), int(close_min)) for open_min, close_min in raw]
    open_min, close_min = data.get("open_min"), data.get("close_min")
    if open_min is not None and close_min is not None:
        return [(int(open_min), int(close_min))]
    return []


async def _begin(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(Booking.date)
    await state.update_data(lang=lang)
    await message.answer(t(lang, "ask_date"), reply_markup=date_kb(lang))


# --- entry points ---
@router.message(
    F.chat.type == "private",
    F.text.func(lambda x: x and _label(x, "btn_book")),
)
async def start_booking(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id)
    if not await is_bookings_enabled():
        await message.answer(
            await get_bookings_closed_text(lang), reply_markup=main_menu_kb(lang)
        )
        return
    await _begin(message, state, lang)


@router.callback_query(F.data == "go:book")
async def start_booking_cb(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await get_lang(callback.from_user.id)
    if not await is_bookings_enabled():
        await callback.message.answer(
            await get_bookings_closed_text(lang), reply_markup=main_menu_kb(lang)
        )
        await callback.answer()
        return
    await _begin(callback.message, state, lang)
    await callback.answer()


# --- global cancel while booking ---
@router.message(
    Booking.date, F.text.func(lambda x: x and _label(x, "btn_cancel"))
)
@router.message(
    Booking.time, F.text.func(lambda x: x and _label(x, "btn_cancel"))
)
@router.message(
    Booking.guests, F.text.func(lambda x: x and _label(x, "btn_cancel"))
)
@router.message(
    Booking.guests_number, F.text.func(lambda x: x and _label(x, "btn_cancel"))
)
@router.message(
    Booking.name, F.text.func(lambda x: x and _label(x, "btn_cancel"))
)
@router.message(
    Booking.phone, F.text.func(lambda x: x and _label(x, "btn_cancel"))
)
@router.message(
    Booking.requests, F.text.func(lambda x: x and _label(x, "btn_cancel"))
)
async def cancel_booking(message: Message, state: FSMContext) -> None:
    lang = (await state.get_data()).get("lang", "ru")
    await state.clear()
    await message.answer(t(lang, "cancelled"), reply_markup=main_menu_kb(lang))


# --- step 1: date ---
async def _ask_time(message: Message, state: FSMContext, lang: str,
                    windows: list[tuple[int, int]]) -> None:
    """Move on to the time step, offering the slots allowed on the chosen day."""
    windows = sort_windows(windows)
    slots = windows_slots(windows)
    prompt = fill(
        t(lang, "ask_time"),
        hours=windows_label(windows),
        # kept so an older admin-edited text using {from}/{to} still renders
        **{"from": fmt_time(windows[0][0]), "to": fmt_time(windows[-1][1])},
    )
    await state.set_state(Booking.time)
    await message.answer(prompt, reply_markup=time_kb(lang, slots))


@router.message(Booking.date, F.text)
async def step_date(message: Message, state: FSMContext) -> None:
    lang = (await state.get_data()).get("lang", "ru")
    text = message.text.strip()

    if _label(text, "btn_today"):
        chosen = date.today()
    elif _label(text, "btn_tomorrow"):
        chosen = date.today() + timedelta(days=1)
    else:
        chosen = parse_date(text)
        if chosen is None:
            await message.answer(t(lang, "date_bad"), reply_markup=date_kb(lang))
            return

    if chosen < date.today():
        await message.answer(t(lang, "date_past"), reply_markup=date_kb(lang))
        return

    available, custom = await check_date(chosen, lang)
    if not available:
        text_out = custom or await get_message("date_closed", lang)
        await message.answer(
            fill(text_out, date=fmt_date(chosen)), reply_markup=date_kb(lang)
        )
        return

    windows = await day_windows(chosen)
    if not windows:  # defensive: check_date already covers this
        await message.answer(
            fill(await get_message("date_closed", lang), date=fmt_date(chosen)),
            reply_markup=date_kb(lang),
        )
        return

    windows = sort_windows(windows)
    await state.update_data(
        date=fmt_date(chosen),
        date_iso=chosen.isoformat(),
        windows=[[open_min, close_min] for open_min, close_min in windows],
    )
    await _ask_time(message, state, lang, windows)


# --- step 2: time ---
@router.message(Booking.time, F.text)
async def step_time(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ru")
    windows = _state_windows(data)

    # no windows in state (e.g. an FSM left over from an older version) —
    # accept the value as typed rather than dead-ending the guest
    if not windows:
        await state.update_data(time=message.text.strip())
        await state.set_state(Booking.guests)
        await message.answer(t(lang, "ask_guests"), reply_markup=guests_kb(lang))
        return

    slots = windows_slots(windows)
    minutes = parse_time(message.text)
    if minutes is None:
        await message.answer(t(lang, "time_bad"), reply_markup=time_kb(lang, slots))
        return

    if not time_in_windows(minutes, windows):
        await message.answer(
            fill(
                await get_message("time_closed", lang),
                hours=windows_label(windows),
                **{"from": fmt_time(windows[0][0]), "to": fmt_time(windows[-1][1])},
            ),
            reply_markup=time_kb(lang, slots),
        )
        return

    await state.update_data(time=fmt_time(minutes))
    await state.set_state(Booking.guests)
    await message.answer(t(lang, "ask_guests"), reply_markup=guests_kb(lang))


# --- step 3: guests ---
@router.message(Booking.guests, F.text)
async def step_guests(message: Message, state: FSMContext) -> None:
    lang = (await state.get_data()).get("lang", "ru")
    text = message.text.strip()
    if _label(text, "btn_guests_more"):
        await state.set_state(Booking.guests_number)
        await message.answer(t(lang, "ask_guests_number"), reply_markup=_cancel_kb(lang))
        return
    await state.update_data(guests=text)
    await state.set_state(Booking.name)
    await message.answer(t(lang, "ask_name"), reply_markup=_cancel_kb(lang))


@router.message(Booking.guests_number, F.text)
async def step_guests_number(message: Message, state: FSMContext) -> None:
    lang = (await state.get_data()).get("lang", "ru")
    await state.update_data(guests=message.text.strip())
    await state.set_state(Booking.name)
    await message.answer(t(lang, "ask_name"), reply_markup=_cancel_kb(lang))


# --- step 4: name ---
@router.message(Booking.name, F.text)
async def step_name(message: Message, state: FSMContext) -> None:
    lang = (await state.get_data()).get("lang", "ru")
    await state.update_data(name=message.text.strip())
    await state.set_state(Booking.phone)
    await message.answer(t(lang, "ask_phone"), reply_markup=phone_kb(lang))


# --- step 5: phone (contact or typed) ---
@router.message(Booking.phone, F.contact)
async def step_phone_contact(message: Message, state: FSMContext) -> None:
    lang = (await state.get_data()).get("lang", "ru")
    await state.update_data(phone=message.contact.phone_number)
    await state.set_state(Booking.requests)
    await message.answer(t(lang, "ask_requests"), reply_markup=requests_kb(lang))


@router.message(Booking.phone, F.text)
async def step_phone_text(message: Message, state: FSMContext) -> None:
    lang = (await state.get_data()).get("lang", "ru")
    await state.update_data(phone=message.text.strip())
    await state.set_state(Booking.requests)
    await message.answer(t(lang, "ask_requests"), reply_markup=requests_kb(lang))


# --- step 6: requests ---
@router.message(Booking.requests, F.text)
async def step_requests(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ru")
    text = message.text.strip()
    requests_value = "" if _label(text, "btn_skip") else text
    await state.update_data(requests=requests_value)
    data = await state.get_data()

    requests_display = esc(requests_value) if requests_value else t(lang, "requests_none")
    card = t(
        lang, "confirm_card",
        date=esc(data["date"]),
        time=esc(data["time"]),
        guests=esc(data["guests"]),
        name=esc(data["name"]),
        phone=esc(data.get("phone", "")),
        requests=requests_display,
    )
    await state.set_state(Booking.confirm)
    # drop the reply keyboard, show inline confirm buttons
    await message.answer(card, reply_markup=confirm_kb(lang))


# --- step 7: confirm actions ---
def _manager_card(booking_id: int, data: dict, user) -> str:
    """The request as managers see it. Large parties get a loud header so they
    can't be missed in a busy group chat."""
    count = guests_count(data["guests"])
    is_large = count is not None and count >= LARGE_PARTY_THRESHOLD

    lang_human = "🇷🇺 русский" if data.get("lang", "ru") == "ru" else "🇬🇧 английский"
    requests_line = esc(data.get("requests")) if data.get("requests") else "—"
    username = f"@{user.username}" if user.username else "—"

    if is_large:
        head = (
            f"❗️❗️❗️ <b>БОЛЬШАЯ КОМПАНИЯ — заявка №{booking_id}</b>\n"
            f"❗️ Гостей: <b>{count}</b> — нужен депозит и сервис 10%\n"
            "➖➖➖➖➖➖➖➖➖➖\n"
        )
        guests_line = f"👥 <b>{esc(data['guests'])}</b> ❗️"
    else:
        head = f"🆕 <b>Новая заявка №{booking_id}</b>\n"
        guests_line = f"👥 {esc(data['guests'])}"

    return (
        f"{head}"
        f"📅 {esc(data['date'])} · 🕐 {esc(data['time'])} · {guests_line}\n"
        f"👤 {esc(data['name'])}\n"
        f"📱 {esc(data.get('phone', '—'))}\n"
        f"💬 {requests_line}\n"
        f"🌐 Клиент пишет: {lang_human}\n"
        f"👥 TG: {username}"
    )


@router.callback_query(Booking.confirm, F.data == "book:send")
async def confirm_send(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ru")
    user = callback.from_user

    booking_id = await db.create_booking(
        tg_id=user.id,
        lang=lang,
        b_date=data["date"],
        b_time=data["time"],
        guests=data["guests"],
        name=data["name"],
        phone=data.get("phone"),
        requests=data.get("requests") or None,
    )

    await callback.bot.send_message(
        config.ADMIN_CHAT_ID,
        _manager_card(booking_id, data, user),
        reply_markup=manager_kb(booking_id),
    )

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(t(lang, "sent"), reply_markup=main_menu_kb(lang))
    await state.clear()
    await callback.answer()


@router.callback_query(Booking.confirm, F.data == "book:edit")
async def confirm_edit(callback: CallbackQuery, state: FSMContext) -> None:
    lang = (await state.get_data()).get("lang", "ru")
    await callback.message.edit_reply_markup(reply_markup=None)
    await _begin(callback.message, state, lang)
    await callback.answer()


@router.callback_query(Booking.confirm, F.data == "book:cancel")
async def confirm_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    lang = (await state.get_data()).get("lang", "ru")
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.clear()
    await callback.message.answer(t(lang, "cancelled"), reply_markup=main_menu_kb(lang))
    await callback.answer()
