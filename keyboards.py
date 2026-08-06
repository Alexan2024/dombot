"""Inline and reply keyboard builders."""
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from texts import t

REMOVE = ReplyKeyboardRemove()


def language_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Русский", callback_data="lang:ru"),
        InlineKeyboardButton(text="English", callback_data="lang:en"),
    ]])


def main_menu_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "btn_book"))],
            [KeyboardButton(text=t(lang, "btn_menu")), KeyboardButton(text=t(lang, "btn_events"))],
            [KeyboardButton(text=t(lang, "btn_hours")), KeyboardButton(text=t(lang, "btn_faq"))],
            [KeyboardButton(text=t(lang, "btn_language"))],
        ],
        resize_keyboard=True,
    )


def date_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "btn_today")), KeyboardButton(text=t(lang, "btn_tomorrow"))],
            [KeyboardButton(text=t(lang, "btn_cancel"))],
        ],
        resize_keyboard=True,
    )


def time_kb(lang: str, slots: list[str]) -> ReplyKeyboardMarkup:
    """Bookable time slots, four per row. The guest may also type a time."""
    rows = [
        [KeyboardButton(text=slot) for slot in slots[i:i + 4]]
        for i in range(0, len(slots), 4)
    ]
    rows.append([KeyboardButton(text=t(lang, "btn_cancel"))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def guests_kb(lang: str) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=str(n)) for n in (1, 2, 3, 4)],
        [KeyboardButton(text=str(n)) for n in (5, 6, 7, 8)],
        [KeyboardButton(text=t(lang, "btn_guests_more"))],
        [KeyboardButton(text=t(lang, "btn_cancel"))],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def phone_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "btn_share_contact"), request_contact=True)],
            [KeyboardButton(text=t(lang, "btn_cancel"))],
        ],
        resize_keyboard=True,
    )


def requests_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "btn_skip"))],
            [KeyboardButton(text=t(lang, "btn_cancel"))],
        ],
        resize_keyboard=True,
    )


def confirm_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn_send"), callback_data="book:send")],
        [
            InlineKeyboardButton(text=t(lang, "btn_edit"), callback_data="book:edit"),
            InlineKeyboardButton(text=t(lang, "btn_cancel"), callback_data="book:cancel"),
        ],
    ])


def manager_kb(booking_id: int) -> InlineKeyboardMarkup:
    """Buttons shown to managers under a new booking request (labels in Russian)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"mgr:confirm:{booking_id}")],
        [
            InlineKeyboardButton(text="🕐 Другое время", callback_data=f"mgr:reschedule:{booking_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"mgr:decline:{booking_id}"),
        ],
    ])


def client_alt_kb(lang: str, booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn_alt_ok"), callback_data=f"alt:ok:{booking_id}")],
        [InlineKeyboardButton(text=t(lang, "btn_alt_other"), callback_data=f"alt:no:{booking_id}")],
    ])


def events_book_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "btn_book"), callback_data="go:book"),
    ]])


def faq_kb(lang: str, items: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    """Build the public FAQ menu from (faq_id, question) pairs."""
    rows = [
        [InlineKeyboardButton(text=question, callback_data=f"faq:item:{faq_id}")]
        for faq_id, question in items
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def faq_back_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "faq_back"), callback_data="faq:menu"),
    ]])
