"""Assemble all routers in the correct order.

Order matters: FSM-driven routers (booking, admin, broadcast, stats, events)
must come before the generic fallback in `info`, which catches any remaining
private-chat text.
"""
from aiogram import Router

from handlers import admin, booking, broadcast, events, info, manager, start, stats


def build_router() -> Router:
    root = Router()
    root.include_router(start.router)      # /start, language, menu, hours
    root.include_router(booking.router)    # booking FSM + confirm
    root.include_router(manager.router)    # manager confirm/reschedule/decline
    root.include_router(admin.router)      # /admin panel: events, FAQ, menu, contacts, toggle
    root.include_router(broadcast.router)  # broadcast FSM
    root.include_router(stats.router)      # statistics panel
    root.include_router(events.router)     # events view + admin add/edit/delete
    root.include_router(info.router)       # FAQ + fallback (LAST)
    return root
