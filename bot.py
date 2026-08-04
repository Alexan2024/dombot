"""Entry point for the ÖMANKÖ DÖM Telegram bot (aiogram 3, long polling)."""
import asyncio
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, TelegramObject

import config
import database as db
from handlers import build_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("omanko-bot")


class ActivityMiddleware(BaseMiddleware):
    """Best-effort logging of guest interactions (private chats only) so the
    statistics panel can report activity, active users and time-in-bot."""

    def __init__(self, kind: str) -> None:
        self.kind = kind

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            user = data.get("event_from_user")
            chat = data.get("event_chat")
            if user and chat is not None and chat.type == "private":
                await db.log_activity(user.id, self.kind)
        except Exception:  # never let logging break message handling
            logger.exception("activity logging failed")
        return await handler(event, data)


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands([
        BotCommand(command="start", description="Меню / Menu"),
        BotCommand(command="language", description="Сменить язык / Change language"),
    ])


async def main() -> None:
    await db.init_db()
    logger.info("Database ready.")

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(ActivityMiddleware("message"))
    dp.callback_query.middleware(ActivityMiddleware("callback"))
    dp.include_router(build_router())

    await set_commands(bot)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Starting polling…")
    try:
        await dp.start_polling(bot)
    finally:
        await db.close_db()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stopped.")
