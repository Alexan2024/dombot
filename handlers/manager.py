"""Manager side: confirm / reschedule / decline, plus the client's reply to an
alternative time. Requests are delivered to ADMIN_CHAT_ID; managers act via buttons."""
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ForceReply, Message

import config
import database as db
from handlers.common import esc
from keyboards import client_alt_kb
from texts import t

router = Router()

_RESCHEDULE_MARKER = "reschedule-request"


def _in_admin_chat(chat_id: int) -> bool:
    return chat_id == config.ADMIN_CHAT_ID


# --- manager: confirm ---
@router.callback_query(F.data.startswith("mgr:confirm:"))
async def mgr_confirm(callback: CallbackQuery) -> None:
    booking_id = int(callback.data.split(":")[2])
    booking = await db.get_booking(booking_id)
    if not booking:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    lang = booking["lang"]
    await db.set_booking_status(booking_id, "confirmed")
    await callback.bot.send_message(
        booking["tg_id"],
        t(lang, "client_confirmed",
          date=esc(booking["b_date"]), time=esc(booking["b_time"]),
          guests=esc(booking["guests"])),
    )
    await callback.message.edit_text(
        callback.message.html_text + f"\n\n✅ <b>Подтверждено</b> (заявка №{booking_id})"
    )
    await callback.answer("Клиенту отправлено подтверждение")


# --- manager: decline ---
@router.callback_query(F.data.startswith("mgr:decline:"))
async def mgr_decline(callback: CallbackQuery) -> None:
    booking_id = int(callback.data.split(":")[2])
    booking = await db.get_booking(booking_id)
    if not booking:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    lang = booking["lang"]
    await db.set_booking_status(booking_id, "declined")
    await callback.bot.send_message(booking["tg_id"], t(lang, "client_declined"))
    await callback.message.edit_text(
        callback.message.html_text + f"\n\n❌ <b>Отклонено</b> (заявка №{booking_id})"
    )
    await callback.answer("Клиенту отправлен отказ")


# --- manager: reschedule (ask for alternative time) ---
@router.callback_query(F.data.startswith("mgr:reschedule:"))
async def mgr_reschedule(callback: CallbackQuery) -> None:
    booking_id = int(callback.data.split(":")[2])
    booking = await db.get_booking(booking_id)
    if not booking:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    await callback.message.answer(
        f"🕐 Напишите альтернативное время для заявки №{booking_id} "
        f"(<i>{_RESCHEDULE_MARKER}</i>) — ответом на это сообщение.",
        reply_markup=ForceReply(selective=False),
    )
    await callback.answer()


# --- manager's reply carrying the alternative time ---
@router.message(
    F.reply_to_message,
    F.chat.id == config.ADMIN_CHAT_ID,
    F.reply_to_message.text.contains(_RESCHEDULE_MARKER),
)
async def mgr_reschedule_reply(message: Message) -> None:
    match = re.search(r"№(\d+)", message.reply_to_message.text or "")
    if not match:
        return
    booking_id = int(match.group(1))
    booking = await db.get_booking(booking_id)
    if not booking:
        await message.reply("Заявка не найдена.")
        return

    alt_time = message.text.strip()
    lang = booking["lang"]
    await db.set_booking_status(booking_id, "reschedule_offered")
    await message.bot.send_message(
        booking["tg_id"],
        t(lang, "client_alt",
          date=esc(booking["b_date"]), time=esc(booking["b_time"]),
          alt_time=esc(alt_time)),
        reply_markup=client_alt_kb(lang, booking_id),
    )
    await message.reply(f"Клиенту предложено время: {esc(alt_time)} (заявка №{booking_id}).")


# --- client accepts the alternative time ---
@router.callback_query(F.data.startswith("alt:ok:"))
async def alt_ok(callback: CallbackQuery) -> None:
    booking_id = int(callback.data.split(":")[2])
    booking = await db.get_booking(booking_id)
    if not booking:
        await callback.answer()
        return

    lang = booking["lang"]
    await db.set_booking_status(booking_id, "confirmed")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(t(lang, "client_alt_accepted"))
    await callback.bot.send_message(
        config.ADMIN_CHAT_ID,
        f"✅ Клиент принял альтернативное время по заявке №{booking_id}.",
    )
    await callback.answer()


# --- client declines the alternative time ---
@router.callback_query(F.data.startswith("alt:no:"))
async def alt_no(callback: CallbackQuery) -> None:
    booking_id = int(callback.data.split(":")[2])
    booking = await db.get_booking(booking_id)
    lang = booking["lang"] if booking else "ru"
    await db.set_booking_status(booking_id, "cancelled")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(t(lang, "client_alt_declined"))
    await callback.bot.send_message(
        config.ADMIN_CHAT_ID,
        f"↩️ Клиент отказался от альтернативного времени по заявке №{booking_id}.",
    )
    await callback.answer()
