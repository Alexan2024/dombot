"""Small helpers shared across handlers."""
import html

import config
import database as db
from texts import t

# in-memory cache of tg_id -> lang to avoid a DB hit on every message
_lang_cache: dict[int, str] = {}

# settings keys for the editable "bookings are closed" message (per language)
BOOKINGS_CLOSED_KEYS = {
    "ru": "msg_bookings_closed_ru",
    "en": "msg_bookings_closed_en",
}


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
    """Booking intake toggle (settings key 'bookings_enabled'). Enabled by default."""
    return (await db.get_setting("bookings_enabled")) != "0"


async def get_content(key: str, default: str) -> str:
    """Editable content (address/hours/phone/...) with a config fallback."""
    value = await db.get_setting(key)
    return value if value is not None else default


def default_bookings_closed(lang: str) -> str:
    """Built-in text from texts.py, used until an admin overrides it."""
    lang = lang if lang in BOOKINGS_CLOSED_KEYS else "ru"
    return t(lang, "bookings_closed")


async def get_bookings_closed_text(lang: str) -> str:
    """Message shown to a guest when booking intake is switched off.

    Editable from the admin panel; falls back to the default in texts.py.
    Stored as HTML (the admin's formatting is preserved).
    """
    lang = lang if lang in BOOKINGS_CLOSED_KEYS else "ru"
    return await get_content(
        BOOKINGS_CLOSED_KEYS[lang], default_bookings_closed(lang)
    )
