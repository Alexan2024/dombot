"""Events: public 'Афиша' view + admin commands (/addevent, /events_admin)."""
from datetime import datetime

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
from handlers.common import esc, get_lang
from keyboards import events_book_kb
from texts import T, t

router = Router()


def _label(text: str, key: str) -> bool:
    return text in (T["ru"][key], T["en"][key])


def _is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def _parse_date(text: str):
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


# ---------- public view ----------
@router.message(
    F.chat.type == "private",
    F.text.func(lambda x: x and _label(x, "btn_events")),
)
async def show_events(message: Message) -> None:
    lang = await get_lang(message.from_user.id)
    events = await db.list_upcoming_events()
    if not events:
        await message.answer(t(lang, "events_empty"))
        return

    lines = [t(lang, "events_header"), ""]
    for e in events:
        d = e["event_date"].strftime("%d.%m.%Y")
        line = f"<b>{d}</b> · {esc(e['title'])}"
        if e["description"]:
            line += f"\n{esc(e['description'])}"
        lines.append(line)
        lines.append("")
    lines.append(t(lang, "events_footer"))
    await message.answer("\n".join(lines), reply_markup=events_book_kb(lang))


# ---------- admin: add event ----------
class AddEvent(StatesGroup):
    date = State()
    title = State()
    desc = State()


@router.message(Command("addevent"))
async def addevent_start(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AddEvent.date)
    await message.answer("Дата события? (в формате ДД.ММ.ГГГГ или ГГГГ-ММ-ДД)")


@router.message(AddEvent.date, F.text)
async def addevent_date(message: Message, state: FSMContext) -> None:
    d = _parse_date(message.text)
    if not d:
        await message.answer("Не понял дату. Пример: 15.08.2025")
        return
    await state.update_data(event_date=d.isoformat())
    await state.set_state(AddEvent.title)
    await message.answer("Название события?")


@router.message(AddEvent.title, F.text)
async def addevent_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip())
    await state.set_state(AddEvent.desc)
    await message.answer("Короткое описание? (или отправьте «-», чтобы пропустить)")


@router.message(AddEvent.desc, F.text)
async def addevent_desc(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    desc = None if message.text.strip() in ("-", "—") else message.text.strip()
    event_id = await db.add_event(
        datetime.fromisoformat(data["event_date"]).date(), data["title"], desc
    )
    await state.clear()
    await message.answer(f"✅ Событие добавлено (№{event_id}).")


# ---------- admin: list / delete events ----------
@router.message(Command("events_admin"))
async def events_admin(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    events = await db.list_upcoming_events()
    if not events:
        await message.answer("Ближайших событий нет.")
        return
    rows = []
    lines = ["<b>Ближайшие события:</b>", ""]
    for e in events:
        d = e["event_date"].strftime("%d.%m.%Y")
        lines.append(f"№{e['id']} · {d} · {esc(e['title'])}")
        rows.append([InlineKeyboardButton(
            text=f"🗑 Удалить №{e['id']}", callback_data=f"evt:del:{e['id']}"
        )])
    await message.answer(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )


@router.callback_query(F.data.startswith("evt:del:"))
async def event_delete(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    event_id = int(callback.data.split(":")[2])
    ok = await db.delete_event(event_id)
    await callback.answer("Удалено" if ok else "Не найдено")
    await callback.message.edit_text(
        callback.message.html_text + f"\n\n🗑 Удалено событие №{event_id}."
    )
