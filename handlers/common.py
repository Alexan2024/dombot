"""Small helpers shared across handlers."""
import html

import config
import database as db

# in-memory cache of tg_id -> lang to avoid a DB hit on every message
_lang_cache: dict[int, str] = {}


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
