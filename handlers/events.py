"""Events: public 'Афиша' view + admin commands (/addevent, /events_admin) +
editing (date / title / description). Admin UI is Russian-only."""
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
def _admin_events_kb(events) -> InlineKeyboardMarkup:
    rows = []
    for e in events:
        rows.append([
            InlineKeyboardButton(text=f"✏️ №{e['id']}", callback_data=f"evt:edit:{e['id']}"),
            InlineKeyboardButton(text=f"🗑 №{e['id']}", callback_data=f"evt:del:{e['id']}"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("events_admin"))
async def events_admin(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    events = await db.list_upcoming_events()
    if not events:
        await message.answer("Ближайших событий нет.")
        return
    lines = ["<b>Ближайшие события:</b>", ""]
    for e in events:
        d = e["event_date"].strftime("%d.%m.%Y")
        lines.append(f"№{e['id']} · {d} · {esc(e['title'])}")
    await message.answer("\n".join(lines), reply_markup=_admin_events_kb(events))


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


# ---------- admin: edit event ----------
class EditEvent(StatesGroup):
    waiting_value = State()


_EVT_FIELD = {
    "date": ("event_date", "📅 Дата (ДД.ММ.ГГГГ или ГГГГ-ММ-ДД)"),
    "title": ("title", "📝 Название"),
    "desc": ("description", "🖊 Описание (или «-», чтобы очистить)"),
}


def _event_edit_kb(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Дата", callback_data=f"evt:efield:{event_id}:date")],
        [InlineKeyboardButton(text="📝 Название", callback_data=f"evt:efield:{event_id}:title")],
        [InlineKeyboardButton(text="🖊 Описание", callback_data=f"evt:efield:{event_id}:desc")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"evt:del:{event_id}")],
    ])


async def _event_card(event_id: int):
    e = await db.get_event(event_id)
    if not e:
        return None, None
    d = e["event_date"].strftime("%d.%m.%Y")
    desc = esc(e["description"]) if e["description"] else "—"
    text = (
        f"🎭 <b>Событие №{event_id}</b>\n\n"
        f"📅 {d}\n"
        f"📝 {esc(e['title'])}\n"
        f"🖊 {desc}\n\n"
        "Что изменить?"
    )
    return text, _event_edit_kb(event_id)


@router.callback_query(F.data.startswith("evt:edit:"))
async def event_edit_menu(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    event_id = int(callback.data.split(":")[2])
    text, kb = await _event_card(event_id)
    if not text:
        await callback.answer("Событие не найдено", show_alert=True)
        return
    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("evt:efield:"))
async def event_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    parts = callback.data.split(":")  # evt efield {id} {field}
    event_id = int(parts[2])
    field = parts[3]
    if field not in _EVT_FIELD:
        await callback.answer()
        return
    await state.set_state(EditEvent.waiting_value)
    await state.update_data(event_id=event_id, field=field)
    await callback.message.answer(
        f"Пришлите новое значение — {_EVT_FIELD[field][1]}.\nДля отмены — /cancel."
    )
    await callback.answer()


@router.message(EditEvent.waiting_value, Command("cancel"))
async def event_edit_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено. Событие не изменилось.")


@router.message(EditEvent.waiting_value, F.text)
async def event_edit_save(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    event_id = data["event_id"]
    field = data["field"]
    column = _EVT_FIELD[field][0]
    value = message.text.strip()

    if field == "date":
        d = _parse_date(value)
        if not d:
            await message.answer("Не понял дату. Пример: 15.08.2025")
            return
        await db.update_event_field(event_id, column, d)
    elif field == "desc":
        new_desc = None if value in ("-", "—") else value
        await db.update_event_field(event_id, column, new_desc)
    else:  # title
        await db.update_event_field(event_id, column, value)

    await state.clear()
    text, kb = await _event_card(event_id)
    await message.answer("✅ Обновлено.")
    if text:
        await message.answer(text, reply_markup=kb)
