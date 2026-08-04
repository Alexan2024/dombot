"""Start, language selection, main menu, menu / hours / language handlers."""
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
import database as db
from handlers.common import get_content, get_lang, set_lang_cache
from keyboards import language_kb, main_menu_kb
from texts import T, t

router = Router()

# settings key under which the menu PDF file_id is stored (see handlers/admin.py)
MENU_FILE_KEY = "menu_file_id"


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(t("ru", "choose_language"), reply_markup=language_kb())


@router.message(Command("language"))
async def cmd_language(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(t("ru", "choose_language"), reply_markup=language_kb())


@router.callback_query(F.data.startswith("lang:"))
async def choose_language(callback: CallbackQuery) -> None:
    lang = callback.data.split(":", 1)[1]
    user = callback.from_user
    await db.upsert_user(user.id, lang, user.username, user.full_name)
    set_lang_cache(user.id, lang)
    await callback.message.answer(t(lang, "main_menu"), reply_markup=main_menu_kb(lang))
    await callback.answer()


# --- Language button from the reply keyboard ---
def _is_label(text: str, key: str) -> bool:
    return text in (T["ru"][key], T["en"][key])


@router.message(
    F.chat.type == "private",
    F.text.func(lambda x: x and _is_label(x, "btn_language")),
)
async def open_language(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(t("ru", "choose_language"), reply_markup=language_kb())


@router.message(
    F.chat.type == "private",
    F.text.func(lambda x: x and _is_label(x, "btn_menu")),
)
async def show_menu(message: Message) -> None:
    lang = await get_lang(message.from_user.id)
    file_id = await db.get_setting(MENU_FILE_KEY)
    if file_id:
        await message.answer_document(file_id, caption=t(lang, "menu_text"))
    elif config.MENU_LINK:
        # backwards-compatible fallback if a link is still configured
        await message.answer(f'{t(lang, "menu_text")}\n{config.MENU_LINK}')
    else:
        await message.answer(t(lang, "menu_no_link"))


@router.message(
    F.chat.type == "private",
    F.text.func(lambda x: x and _is_label(x, "btn_hours")),
)
async def show_hours(message: Message) -> None:
    lang = await get_lang(message.from_user.id)
    await message.answer(
        t(
            lang, "hours_text",
            address=await get_content("info_address", config.ADDRESS),
            working_hours=await get_content("info_hours", config.WORKING_HOURS),
            phone=await get_content("info_phone", config.PHONE),
            map_link=await get_content("info_map_link", config.MAP_LINK),
        ),
        disable_web_page_preview=True,
    )
