"""Broadcast (рассылка): an admin composes any message, picks the audience,
confirms, and the bot copies it to guests with throttling and error handling.

Uses bot.copy_message so text, photos, documents — anything — go out as-is.
Entry point is the "📣 Рассылка" button (callback bc:start) on the admin panel.
"""
import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import database as db
from handlers.common import is_admin

router = Router()
logger = logging.getLogger("omanko-bot.broadcast")

# throttle: ~20 messages/sec to stay well within Telegram limits
_SEND_DELAY = 0.05


class Broadcast(StatesGroup):
    composing = State()
    confirming = State()


def _target_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Всем", callback_data="bc:target:all")],
        [
            InlineKeyboardButton(text="🇷🇺 Русскоязычным", callback_data="bc:target:ru"),
            InlineKeyboardButton(text="🇬🇧 Англоязычным", callback_data="bc:target:en"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="bc:cancel")],
    ])


def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить", callback_data="bc:go")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="bc:cancel")],
    ])


@router.callback_query(F.data == "bc:start")
async def bc_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(Broadcast.composing)
    await callback.message.answer(
        "📣 <b>Рассылка</b>\n\n"
        "Пришлите сообщение для рассылки одним сообщением — текст, фото, документ, "
        "что угодно. Оно будет отправлено гостям как есть.\n\n"
        "Для отмены — /cancel."
    )
    await callback.answer()


@router.message(Broadcast.composing, Command("cancel"))
async def bc_compose_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Рассылка отменена.")


@router.message(Broadcast.composing)
async def bc_compose(message: Message, state: FSMContext) -> None:
    await state.update_data(from_chat_id=message.chat.id, message_id=message.message_id)
    await state.set_state(Broadcast.confirming)
    await message.answer("Кому отправить?", reply_markup=_target_kb())


@router.callback_query(Broadcast.confirming, F.data.startswith("bc:target:"))
async def bc_target(callback: CallbackQuery, state: FSMContext) -> None:
    target = callback.data.split(":")[2]  # all | ru | en
    lang = None if target == "all" else target
    uids = await db.list_user_ids(lang)
    await state.update_data(target=target)
    label = {"all": "всем", "ru": "русскоязычным", "en": "англоязычным"}[target]
    await callback.message.edit_text(
        f"Отправить рассылку <b>{label}</b> — получателей: <b>{len(uids)}</b>?",
        reply_markup=_confirm_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "bc:cancel")
async def bc_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await callback.message.edit_text("Рассылка отменена.")
    except Exception:
        pass
    await callback.answer()


async def _run_broadcast(bot: Bot, from_chat_id: int, message_id: int, target: str):
    lang = None if target == "all" else target
    uids = await db.list_user_ids(lang)
    sent = blocked = failed = 0
    for uid in uids:
        try:
            await bot.copy_message(
                chat_id=uid, from_chat_id=from_chat_id, message_id=message_id
            )
            sent += 1
        except TelegramForbiddenError:
            blocked += 1
            try:
                await db.set_user_blocked(uid, True)
            except Exception:
                logger.exception("failed to mark user %s blocked", uid)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await bot.copy_message(
                    chat_id=uid, from_chat_id=from_chat_id, message_id=message_id
                )
                sent += 1
            except Exception:
                failed += 1
        except TelegramBadRequest:
            failed += 1
        except Exception:
            failed += 1
            logger.exception("broadcast send failed for %s", uid)
        await asyncio.sleep(_SEND_DELAY)
    return sent, blocked, failed


@router.callback_query(Broadcast.confirming, F.data == "bc:go")
async def bc_go(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    data = await state.get_data()
    await state.clear()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    status = await callback.message.answer("📣 Рассылка запущена…")
    await callback.answer()

    sent, blocked, failed = await _run_broadcast(
        callback.bot, data["from_chat_id"], data["message_id"], data["target"]
    )
    await status.edit_text(
        "✅ Рассылка завершена.\n\n"
        f"📨 Отправлено: <b>{sent}</b>\n"
        f"🚫 Заблокировали бота: <b>{blocked}</b>\n"
        f"⚠️ Ошибки: <b>{failed}</b>"
    )
