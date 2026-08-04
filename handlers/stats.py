"""Statistics panel (📊). Opened from the admin panel (callback stats:open).

Sections: overview, users, bookings, activity (interactions, sessions,
time-in-bot). Time-in-bot is computed from the `activity` log, so it only
accumulates for interactions that happen after this feature is deployed.
"""
from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import database as db
from handlers.common import esc, is_admin

router = Router()


def _dur(seconds) -> str:
    seconds = int(seconds or 0)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h and m:
        return f"{h} ч {m} мин"
    if h:
        return f"{h} ч"
    return f"{m} мин"


def _stats_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👥 Пользователи", callback_data="stats:users"),
            InlineKeyboardButton(text="📅 Брони", callback_data="stats:bookings"),
        ],
        [InlineKeyboardButton(text="⏱ Активность", callback_data="stats:activity")],
        [
            InlineKeyboardButton(text="🔄 Сводка", callback_data="stats:overview"),
            InlineKeyboardButton(text="✖️ Закрыть", callback_data="stats:close"),
        ],
    ])


async def _overview_text() -> str:
    u = await db.get_user_stats()
    b = await db.get_booking_stats()
    a = await db.get_activity_stats()
    au = await db.get_active_users()
    ev = await db.count_upcoming_events()
    rate = (b["confirmed"] / b["total"] * 100) if b["total"] else 0
    return (
        "📊 <b>Статистика — сводка</b>\n\n"
        f"👥 Пользователей: <b>{u['total']}</b> (+{u['new_7d']} за 7 дней)\n"
        f"🟢 Активны за 7 дней: <b>{au['active_7d']}</b>\n"
        f"📅 Броней всего: <b>{b['total']}</b>\n"
        f"✅ Успешных: <b>{b['confirmed']}</b> ({rate:.0f}%)\n"
        f"⏳ Ждут ответа: <b>{b['pending']}</b>\n"
        f"🎭 Предстоящих событий: <b>{ev}</b>\n"
        f"💬 Взаимодействий: <b>{a['total']}</b>"
    )


async def _users_text() -> str:
    u = await db.get_user_stats()
    au = await db.get_active_users()
    return (
        "👥 <b>Пользователи</b>\n\n"
        f"Всего: <b>{u['total']}</b>\n"
        f"Новых за сутки: <b>{u['new_1d']}</b>\n"
        f"Новых за 7 дней: <b>{u['new_7d']}</b>\n"
        f"Новых за 30 дней: <b>{u['new_30d']}</b>\n\n"
        f"🇷🇺 Русский: <b>{u['ru']}</b>\n"
        f"🇬🇧 English: <b>{u['en']}</b>\n"
        f"🚫 Заблокировали бота: <b>{u['blocked']}</b>\n\n"
        f"Активны за сутки: <b>{au['active_1d']}</b>\n"
        f"Активны за 7 дней: <b>{au['active_7d']}</b>\n"
        f"Активны за 30 дней: <b>{au['active_30d']}</b>"
    )


async def _bookings_text() -> str:
    b = await db.get_booking_stats()
    times = await db.top_booking_times(5)
    dates = await db.top_booking_dates(5)
    rate = (b["confirmed"] / b["total"] * 100) if b["total"] else 0

    def _lines(rows):
        if not rows:
            return "—"
        return "\n".join(f"• {esc(str(r['v']))} — {r['c']}" for r in rows)

    return (
        "📅 <b>Брони</b>\n\n"
        f"Всего: <b>{b['total']}</b>\n"
        f"⏳ Ожидают: <b>{b['pending']}</b>\n"
        f"✅ Подтверждены: <b>{b['confirmed']}</b>\n"
        f"🕐 Предложено другое время: <b>{b['reschedule_offered']}</b>\n"
        f"❌ Отклонены: <b>{b['declined']}</b>\n"
        f"↩️ Отменены: <b>{b['cancelled']}</b>\n\n"
        f"Доля успешных: <b>{rate:.0f}%</b>\n\n"
        f"За сутки: <b>{b['d1']}</b> · за 7 дней: <b>{b['d7']}</b> · за 30 дней: <b>{b['d30']}</b>\n\n"
        f"<b>Популярное время:</b>\n{_lines(times)}\n\n"
        f"<b>Популярные даты:</b>\n{_lines(dates)}"
    )


async def _activity_text() -> str:
    a = await db.get_activity_stats()
    s = await db.get_session_stats(15)
    return (
        "⏱ <b>Активность</b>\n\n"
        f"Взаимодействий всего: <b>{a['total']}</b>\n"
        f"💬 Сообщений: <b>{a['messages']}</b>\n"
        f"🔘 Нажатий кнопок: <b>{a['callbacks']}</b>\n\n"
        f"За сутки: <b>{a['d1']}</b> · за 7 дней: <b>{a['d7']}</b>\n\n"
        f"🧭 Сессий: <b>{s['session_count']}</b>\n"
        f"⏱ Всего времени в боте: <b>{_dur(s['total_seconds'])}</b>\n"
        f"⌀ Средняя сессия: <b>{_dur(s['avg_seconds'])}</b>\n\n"
        "<i>Время считается по сессиям и накапливается с момента запуска "
        "статистики.</i>"
    )


@router.callback_query(F.data == "stats:open")
async def stats_open(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await callback.message.answer(await _overview_text(), reply_markup=_stats_kb())
    await callback.answer()


async def _edit(callback: CallbackQuery, text: str) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=_stats_kb())
    except Exception:
        # message unchanged or too old to edit — send a fresh one
        await callback.message.answer(text, reply_markup=_stats_kb())


@router.callback_query(F.data == "stats:overview")
async def stats_overview(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await _edit(callback, await _overview_text())
    await callback.answer()


@router.callback_query(F.data == "stats:users")
async def stats_users(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await _edit(callback, await _users_text())
    await callback.answer()


@router.callback_query(F.data == "stats:bookings")
async def stats_bookings(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await _edit(callback, await _bookings_text())
    await callback.answer()


@router.callback_query(F.data == "stats:activity")
async def stats_activity(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await _edit(callback, await _activity_text())
    await callback.answer()


@router.callback_query(F.data == "stats:close")
async def stats_close(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    try:
        await callback.message.edit_text("📊 Статистика закрыта.")
    except Exception:
        pass
    await callback.answer()
