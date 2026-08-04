"""Admin control panel (buttons instead of remembering commands).

- /admin  -> inline panel: events management + menu (PDF) update.
- Events: reuses the AddEvent FSM and the `evt:del:` delete callback from events.py.
- Menu:   admin uploads a PDF once; its Telegram file_id is stored in `settings`
          and re-sent to guests who tap the "Menu" button.

Admin UI is Russian-only, matching the rest of the manager-facing side.
"""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config
import database as db
from handlers.common import esc
from handlers.events import AddEvent  # reuse the existing add-event wizard

router = Router()

MENU_FILE_KEY = "menu_file_id"


def _is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


class SetMenu(StatesGroup):
    waiting_file = State()


def _panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎭 События (просмотр / удаление)", callback_data="adm:events"
        )],
        [InlineKeyboardButton(
            text="➕ Добавить событие", callback_data="adm:addevent"
        )],
        [InlineKeyboardButton(
            text="📎 Обновить меню (PDF)", callback_data="adm:menu"
        )],
    ])


async def _events_list_kb():
    """Build the admin events list text + keyboard (delete buttons + add)."""
    events = await db.list_upcoming_events()
    if not events:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить событие", callback_data="adm:addevent")],
        ])
        return "Ближайших событий нет.", kb

    lines = ["<b>Ближайшие события:</b>", ""]
    rows = []
    for e in events:
        d = e["event_date"].strftime("%d.%m.%Y")
        lines.append(f"№{e['id']} · {d} · {esc(e['title'])}")
        rows.append([InlineKeyboardButton(
            text=f"🗑 Удалить №{e['id']}", callback_data=f"evt:del:{e['id']}"
        )])
    rows.append([InlineKeyboardButton(text="➕ Добавить событие", callback_data="adm:addevent")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- panel entry ----------
@router.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("⚙️ <b>Панель администратора</b>", reply_markup=_panel_kb())


# ---------- events: view / delete ----------
@router.callback_query(F.data == "adm:events")
async def adm_events(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    text, kb = await _events_list_kb()
    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


# ---------- events: add (hands off to the AddEvent wizard in events.py) ----------
@router.callback_query(F.data == "adm:addevent")
async def adm_addevent(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AddEvent.date)
    await callback.message.answer("Дата события? (в формате ДД.ММ.ГГГГ или ГГГГ-ММ-ДД)")
    await callback.answer()


# ---------- menu: update PDF ----------
@router.callback_query(F.data == "adm:menu")
async def adm_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(SetMenu.waiting_file)
    await callback.message.answer(
        "📎 Пришлите PDF-файл с меню одним сообщением (как документ).\n"
        "Он заменит текущее меню, которое видят гости по кнопке «Меню».\n\n"
        "Для отмены — /cancel."
    )
    await callback.answer()


@router.message(SetMenu.waiting_file, Command("cancel"))
async def setmenu_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено. Меню осталось прежним.")


@router.message(SetMenu.waiting_file, F.document)
async def setmenu_file(message: Message, state: FSMContext) -> None:
    doc = message.document
    is_pdf = (
        doc.mime_type == "application/pdf"
        or (doc.file_name or "").lower().endswith(".pdf")
    )
    if not is_pdf:
        await message.answer("Нужен именно PDF. Пришлите документ в формате PDF или /cancel.")
        return
    await db.set_setting(MENU_FILE_KEY, doc.file_id)
    await state.clear()
    await message.answer(
        "✅ Меню обновлено. Теперь гости получают этот файл по кнопке «Меню»."
    )


@router.message(SetMenu.waiting_file, F.text)
async def setmenu_wrong(message: Message) -> None:
    await message.answer("Жду PDF-файл (как документ). Или /cancel для отмены.")
