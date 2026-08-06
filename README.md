# ÖMANKÖ DÖM — Telegram bot

Bilingual (RU/EN) Telegram bot for the ÖMANKÖ DÖM restaurant:

- **Table booking** — the guest answers a few questions, the request is delivered
  to a managers' chat as a formatted card. A manager confirms, offers another
  time, or declines with one tap; the guest gets the answer automatically.
- **Menu**, **Hours & location**, **FAQ**.
- **Events (Афиша)** — upcoming events, editable by admins right inside Telegram.

Stack: Python + [aiogram 3](https://docs.aiogram.dev) + PostgreSQL, long polling.
Designed to run on [Railway](https://railway.app).

---

## 1. Create the bot

1. Open [@BotFather](https://t.me/BotFather) → `/newbot` → get the **BOT_TOKEN**.
2. Create a Telegram **group** for your managers and add the bot to it.
3. Get the group's **chat id** (`ADMIN_CHAT_ID`): temporarily add
   [@getmyid_bot](https://t.me/getmyid_bot) or [@RawDataBot](https://t.me/RawDataBot)
   to the group — the chat id is the negative number (e.g. `-1001234567890`).
4. Get **your own user id** (`ADMIN_IDS`) from [@getmyid_bot](https://t.me/getmyid_bot)
   in a private chat. Add every manager who should be able to manage events.

> Managers act on requests via the buttons in the group — they don't need to be
> in `ADMIN_IDS`. `ADMIN_IDS` only gates event commands (`/addevent`, `/events_admin`).

## 2. Deploy on Railway

1. Push this folder to a GitHub repo.
2. In Railway: **New Project → Deploy from GitHub repo**, pick the repo.
3. Add a database: **New → Database → PostgreSQL**. Railway injects `DATABASE_URL`
   automatically into the service.
4. Open the service → **Variables** and add:
   - `BOT_TOKEN`
   - `ADMIN_CHAT_ID`
   - `ADMIN_IDS`
   - (optional) `ADDRESS`, `WORKING_HOURS`, `PHONE`, `MAP_LINK`, `MENU_LINK`
5. Deploy. Railway runs `python bot.py` (see `railway.json` / `Procfile`).
   Tables are created automatically on first start.

That's it — open the bot in Telegram and press **Start**.

## 3. Run locally (optional)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in the values, incl. a local DATABASE_URL
python bot.py
```

## 4. Booking availability

All of this lives under `/admin`:

- **📅 Закрытые даты** — switch booking off for a specific day. Optionally give
  that date its own RU/EN message; otherwise guests see the general
  "date closed" text, which is editable in the same section.
- **🕐 Часы бронирования** — a bookable window per weekday
  (`12:00-23:00`, or `12:00-01:00` for a window crossing midnight), or mark the
  day as **выходной**. Guests get time-slot buttons built from that window and
  can still type a time; anything outside the window is rejected with an
  editable message.
- **🔕 Приём броней** — the global kill switch, unchanged.

Defaults on first start: 12:00–23:00 every day. Check the panel right after
deploying and adjust.

## 5. Managing events

In the managers' chat (or private chat with the bot), an admin sends:

- `/addevent` — wizard: date → title → description.
- `/events_admin` — list upcoming events with delete buttons.

Guests see them under the **🎭 Афиша / Events** button.

## 6. Filling in content

- Restaurant address / hours / phone / map / menu link → Railway **Variables**
  (or edit defaults in `config.py`).
- FAQ answers → edit the `faq_a_*` strings in `texts.py` (currently placeholders).
- Wording of any message → `texts.py` (all RU/EN strings live there).

## Project layout

```
bot.py              entry point (polling)
config.py           reads environment variables
texts.py            all RU/EN strings and button labels
database.py         PostgreSQL access (users, bookings, events)
keyboards.py        inline / reply keyboards
handlers/
  start.py          /start, language, main menu, menu, hours
  booking.py        booking conversation + confirmation
  manager.py        confirm / reschedule / decline + client's reply
  events.py         events view + admin add/list/delete
  info.py           FAQ + fallback
  common.py         shared helpers
```

## Booking status flow

`pending` → `confirmed` | `declined` | `reschedule_offered` → `confirmed` | `cancelled`
