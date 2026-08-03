"""PostgreSQL access layer (asyncpg). Tables are created on startup."""
import asyncpg

from config import DATABASE_URL

_pool: asyncpg.Pool | None = None


async def init_db() -> None:
    """Create the connection pool and ensure tables exist."""
    global _pool
    _pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=5)
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                tg_id      BIGINT PRIMARY KEY,
                lang       TEXT NOT NULL DEFAULT 'ru',
                username   TEXT,
                full_name  TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id         SERIAL PRIMARY KEY,
                tg_id      BIGINT NOT NULL,
                lang       TEXT NOT NULL DEFAULT 'ru',
                b_date     TEXT NOT NULL,
                b_time     TEXT NOT NULL,
                guests     TEXT NOT NULL,
                name       TEXT NOT NULL,
                phone      TEXT,
                requests   TEXT,
                status     TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS events (
                id          SERIAL PRIMARY KEY,
                event_date  DATE NOT NULL,
                title       TEXT NOT NULL,
                description TEXT,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )


async def close_db() -> None:
    if _pool:
        await _pool.close()


# --- users ---
async def upsert_user(tg_id: int, lang: str, username: str | None, full_name: str | None) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (tg_id, lang, username, full_name)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (tg_id) DO UPDATE
              SET lang = EXCLUDED.lang,
                  username = EXCLUDED.username,
                  full_name = EXCLUDED.full_name;
            """,
            tg_id, lang, username, full_name,
        )


async def get_user_lang(tg_id: int) -> str | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT lang FROM users WHERE tg_id = $1", tg_id)
        return row["lang"] if row else None


# --- bookings ---
async def create_booking(
    tg_id: int, lang: str, b_date: str, b_time: str, guests: str,
    name: str, phone: str | None, requests: str | None,
) -> int:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO bookings (tg_id, lang, b_date, b_time, guests, name, phone, requests)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id;
            """,
            tg_id, lang, b_date, b_time, guests, name, phone, requests,
        )
        return row["id"]


async def get_booking(booking_id: int) -> asyncpg.Record | None:
    async with _pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM bookings WHERE id = $1", booking_id)


async def set_booking_status(booking_id: int, status: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE bookings SET status = $2 WHERE id = $1", booking_id, status
        )


# --- events ---
async def add_event(event_date, title: str, description: str | None) -> int:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO events (event_date, title, description)
            VALUES ($1, $2, $3) RETURNING id;
            """,
            event_date, title, description,
        )
        return row["id"]


async def list_upcoming_events() -> list[asyncpg.Record]:
    async with _pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT * FROM events
            WHERE event_date >= CURRENT_DATE
            ORDER BY event_date ASC;
            """
        )


async def delete_event(event_id: int) -> bool:
    async with _pool.acquire() as conn:
        result = await conn.execute("DELETE FROM events WHERE id = $1", event_id)
        return result.endswith("1")
