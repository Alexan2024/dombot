"""Configuration loaded from environment variables (Railway variables)."""
import os

from dotenv import load_dotenv

load_dotenv()  # loads .env locally; on Railway variables come from the dashboard


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Set it in Railway → Variables (or in a local .env file)."
        )
    return value


# --- Telegram ---
BOT_TOKEN: str = _require("BOT_TOKEN")

# Chat where new booking requests are delivered (a group with your managers).
# Negative number for groups, e.g. -1001234567890.
ADMIN_CHAT_ID: int = int(_require("ADMIN_CHAT_ID"))

# User IDs allowed to run admin commands (/addevent, /events_admin, ...).
# Comma-separated list of numeric Telegram user IDs.
ADMIN_IDS: set[int] = {
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
}

# --- Database (Railway provides DATABASE_URL automatically once you add Postgres) ---
DATABASE_URL: str = _require("DATABASE_URL")

# --- Restaurant static content (safe defaults; override via env if you like) ---
RESTAURANT_NAME = "ÖMANKÖ DÖM"
ADDRESS = os.getenv("ADDRESS", "г. Москва, ул. Примерная, 1")
WORKING_HOURS = os.getenv("WORKING_HOURS", "Пн–Вс, 12:00–00:00")
PHONE = os.getenv("PHONE", "+7 (000) 000-00-00")
MAP_LINK = os.getenv("MAP_LINK", "https://maps.google.com")
MENU_LINK = os.getenv("MENU_LINK", "")  # optional PDF/site link for the menu
