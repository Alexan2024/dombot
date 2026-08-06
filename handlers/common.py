"""Small helpers shared across handlers: language cache, escaping, editable
guest-facing messages, date/time parsing and booking-availability checks."""
import html
import re
from datetime import date, datetime

import config
import database as db
from texts import t

# in-memory cache of tg_id -> lang to avoid a DB hit on every message
_lang_cache: dict[int, str] = {}

LANGS = ("ru", "en")

# Guest-facing messages an admin can rewrite from the panel.
# Settings key is msg_{name}_{lang}; the fallback lives in texts.py under {name}.
EDITABLE_MESSAGES = ("bookings_closed", "date_closed", "time_closed")

# kept for backwards compatibility with earlier code / stored settings
BOOKINGS_CLOSED_KEYS = {
    "ru": "msg_bookings_closed_ru",
    "en": "msg_bookings_closed_en",
}

WEEKDAYS_RU = ("Понедельник", "Вторник", "Среда", "Четверг",
               "Пятница", "Суббота", "Воскресенье")
WEEKDAYS_RU_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")

SLOT_STEP_MINUTES = 30


async def get_lang(tg_id: int) -> str:
    """Resolve a user's language, defaulting to Russian."""
    if tg_id in _lang_cache:
        return _lang_cache[tg_id]
    lang = await db.get_user_lang(tg_id) or "ru"
    _lang_cache[tg_id] = lang
    return lang


def set_lang_cache(tg_id: int, lang: str) -> None:
    _lang_cache[tg_id] = lang


def esc(value: str | None) -> str:
    """Escape user-provided text before embedding into HTML messages."""
    return html.escape(value) if value else ""


def is_admin(user_id: int) -> bool:
    """Whether the user may use admin commands / the control panel."""
    return user_id in config.ADMIN_IDS


async def is_bookings_enabled() -> bool:
    """Global booking-intake toggle ('bookings_enabled'). Enabled by default."""
    return (await db.get_setting("bookings_enabled")) != "0"


async def get_content(key: str, default: str) -> str:
    """Editable content (address/hours/phone/...) with a config fallback."""
    value = await db.get_setting(key)
    return value if value is not None else default


# ---------- editable guest-facing messages ----------
def message_key(name: str, lang: str) -> str:
    """Settings key holding the admin-edited version of a message."""
    lang = lang if lang in LANGS else "ru"
    return f"msg_{name}_{lang}"


def default_message(name: str, lang: str) -> str:
    """Built-in text from texts.py, used until an admin overrides it."""
    lang = lang if lang in LANGS else "ru"
    return t(lang, name)


async def get_message(name: str, lang: str) -> str:
    """Guest-facing message, editable from the admin panel.

    Stored as HTML so the admin's Telegram formatting is preserved.
    """
    lang = lang if lang in LANGS else "ru"
    return await get_content(message_key(name, lang), default_message(name, lang))


def fill(template: str, **values) -> str:
    """Substitute {placeholders} without str.format, so an admin-edited text
    containing stray braces can never raise."""
    for key, value in values.items():
        template = template.replace("{" + key + "}", str(value))
    return template


# thin wrappers kept so existing imports keep working
def default_bookings_closed(lang: str) -> str:
    return default_message("bookings_closed", lang)


async def get_bookings_closed_text(lang: str) -> str:
    return await get_message("bookings_closed", lang)


# ---------- date helpers ----------
_DATE_FORMATS = ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y")


def parse_date(text: str) -> date | None:
    """Parse a date the guest or an admin typed. Returns None if unrecognised."""
    raw = (text or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    # bare day.month -> nearest occurrence, this year or the next
    match = re.fullmatch(r"(\d{1,2})[.\-/](\d{1,2})", raw)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        today = date.today()
        for year in (today.year, today.year + 1):
            try:
                candidate = date(year, month, day)
            except ValueError:
                return None
            if candidate >= today:
                return candidate
    return None


def fmt_date(day: date) -> str:
    return day.strftime("%d.%m.%Y")


# ---------- time helpers ----------
_TIME_RE = re.compile(r"^(\d{1,2})\s*[:.\-\s]?\s*(\d{2})?$")


def parse_time(text: str) -> int | None:
    """Parse '19:30', '19.30', '1930', '19' -> minutes from midnight."""
    match = _TIME_RE.match((text or "").strip())
    if not match:
        return None
    hours = int(match.group(1))
    minutes = int(match.group(2) or 0)
    if hours == 24 and minutes == 0:
        return 0
    if hours > 23 or minutes > 59:
        return None
    return hours * 60 + minutes


def fmt_time(minutes: int) -> str:
    minutes %= 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _normalized_window(open_min: int, close_min: int) -> tuple[int, int]:
    """Return (open, close) with close pushed past midnight when needed."""
    return open_min, close_min if close_min > open_min else close_min + 1440


def time_in_window(minutes: int, open_min: int, close_min: int) -> bool:
    start, end = _normalized_window(open_min, close_min)
    value = minutes if minutes >= start else minutes + 1440
    return start <= value <= end


def time_slots(open_min: int, close_min: int, step: int = SLOT_STEP_MINUTES) -> list[str]:
    """Bookable times inside the window, as HH:MM labels."""
    start, end = _normalized_window(open_min, close_min)
    return [fmt_time(m) for m in range(start, end + 1, step)]


def window_label(open_min: int, close_min: int) -> str:
    return f"{fmt_time(open_min)}–{fmt_time(close_min)}"


# ---------- availability ----------
async def day_window(day: date) -> tuple[int, int] | None:
    """Bookable window for a given day, or None if the weekday is a day off."""
    hours = await db.get_booking_hours(day.weekday())
    if not hours or not hours["is_open"]:
        return None
    return hours["open_min"], hours["close_min"]


async def check_date(day: date, lang: str) -> tuple[bool, str | None]:
    """(available, custom_message).

    A day is unavailable when it is explicitly blocked or falls on a weekday
    marked as a day off. `custom_message` is the per-date text an admin wrote,
    when there is one; otherwise the caller uses the general message.
    """
    blocked = await db.get_blocked_date(day)
    if blocked:
        custom = blocked["message_ru"] if lang == "ru" else blocked["message_en"]
        return False, (custom or None)
    if await day_window(day) is None:
        return False, None
    return True, None
