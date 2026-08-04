"""Assemble all routers in the correct order.

Order matters: FSM-driven routers (booking, events-admin, admin) must come
before the generic fallback in `info`, which catches any remaining text.
"""
from aiogram import Router

from handlers import admin, booking, events, info, manager, start


def build_router() -> Router:
    root = Router()
    root.include_router(start.router)     # /start, language, menu, hours
    root.include_router(booking.router)   # booking FSM + confirm
    root.include_router(manager.router)   # manager confirm/reschedule/decline
    root.include_router(admin.router)     # /admin panel + menu (PDF) update
    root.include_router(events.router)    # events view + admin commands
    root.include_router(info.router)      # FAQ + fallback (LAST)
    return root
