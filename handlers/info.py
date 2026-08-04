"""FAQ menu (now database-driven, editable from the admin panel) and a
fallback for unrecognized input. Included LAST."""
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

import database as db
from handlers.common import esc, get_lang
from keyboards import faq_back_kb, faq_kb, main_menu_kb
from texts import T, t

router = Router()


def _label(text: str, key: str) -> bool:
    return text in (T["ru"][key], T["en"][key])


def _question(item, lang: str) -> str:
    return item["question_ru"] if lang == "ru" else item["question_en"]


def _answer(item, lang: str) -> str:
    return item["answer_ru"] if lang == "ru" else item["answer_en"]


async def _faq_pairs(lang: str):
    items = await db.list_faq()
    return items, [(e["id"], _question(e, lang)) for e in items]


@router.message(
    F.chat.type == "private",
    F.text.func(lambda x: x and _label(x, "btn_faq")),
)
async def show_faq(message: Message) -> None:
    lang = await get_lang(message.from_user.id)
    items, pairs = await _faq_pairs(lang)
    if not items:
        await message.answer(t(lang, "faq_empty"))
        return
    await message.answer(t(lang, "faq_header"), reply_markup=faq_kb(lang, pairs))


@router.callback_query(F.data == "faq:menu")
async def faq_menu(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    items, pairs = await _faq_pairs(lang)
    if not items:
        await callback.message.edit_text(t(lang, "faq_empty"))
        await callback.answer()
        return
    await callback.message.edit_text(t(lang, "faq_header"), reply_markup=faq_kb(lang, pairs))
    await callback.answer()


@router.callback_query(F.data.startswith("faq:item:"))
async def faq_item(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    faq_id = int(callback.data.split(":")[2])
    item = await db.get_faq(faq_id)
    if not item:
        await callback.answer()
        return
    text = f"<b>{esc(_question(item, lang))}</b>\n\n{esc(_answer(item, lang))}"
    await callback.message.edit_text(text, reply_markup=faq_back_kb(lang))
    await callback.answer()


# --- fallback for anything not handled above ---
# Restricted to PRIVATE chats so the bot never replies to normal chatter
# in the managers' group.
@router.message(F.chat.type == "private", F.text)
async def fallback(message: Message) -> None:
    lang = await get_lang(message.from_user.id)
    await message.answer(t(lang, "unknown"), reply_markup=main_menu_kb(lang))
