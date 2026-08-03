"""Small helpers shared across handlers."""
import html

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
