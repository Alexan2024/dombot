"""FAQ menu and a fallback for unrecognized input. Included LAST."""
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from handlers.common import get_lang
from keyboards import faq_back_kb, faq_kb, main_menu_kb
from texts import T, t

router = Router()

_FAQ_ANSWERS = {
    "parking": "faq_a_parking",
    "kids": "faq_a_kids",
    "pets": "faq_a_pets",
    "dresscode": "faq_a_dresscode",
    "terrace": "faq_a_terrace",
}


def _label(text: str, key: str) -> bool:
    return text in (T["ru"][key], T["en"][key])


@router.message(F.text.func(lambda x: x and _label(x, "btn_faq")))
async def show_faq(message: Message) -> None:
    lang = await get_lang(message.from_user.id)
    await message.answer(t(lang, "faq_header"), reply_markup=faq_kb(lang))


@router.callback_query(F.data == "faq:menu")
async def faq_menu(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    await callback.message.edit_text(t(lang, "faq_header"), reply_markup=faq_kb(lang))
    await callback.answer()


@router.callback_query(F.data.startswith("faq:"))
async def faq_answer(callback: CallbackQuery) -> None:
    lang = await get_lang(callback.from_user.id)
    key = callback.data.split(":", 1)[1]
    answer_key = _FAQ_ANSWERS.get(key)
    if not answer_key:
        await callback.answer()
        return
    await callback.message.edit_text(t(lang, answer_key), reply_markup=faq_back_kb(lang))
    await callback.answer()


# --- fallback for anything not handled above ---
@router.message(F.text)
async def fallback(message: Message) -> None:
    lang = await get_lang(message.from_user.id)
    await message.answer(t(lang, "unknown"), reply_markup=main_menu_kb(lang))
