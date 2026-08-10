"""PostgreSQL access layer (asyncpg). Tables are created / migrated on startup."""
import asyncpg

from config import DATABASE_URL

_pool: asyncpg.Pool | None = None

# default bookable window seeded on a brand-new database: 12:00-23:00 daily
_DEFAULT_OPEN_MIN = 720
_DEFAULT_CLOSE_MIN = 1380


async def init_db() -> None:
    """Create the connection pool, ensure tables exist, run light migrations."""
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

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS faq (
                id          SERIAL PRIMARY KEY,
                position    INTEGER NOT NULL DEFAULT 0,
                question_ru TEXT NOT NULL,
                question_en TEXT NOT NULL,
                answer_ru   TEXT NOT NULL,
                answer_en   TEXT NOT NULL,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS activity (
                id         BIGSERIAL PRIMARY KEY,
                tg_id      BIGINT NOT NULL,
                kind       TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            -- dates on which booking is switched off (optional custom message)
            CREATE TABLE IF NOT EXISTS blocked_dates (
                day        DATE PRIMARY KEY,
                message_ru TEXT,
                message_en TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            -- LEGACY: a single window per weekday. Superseded by booking_windows;
            -- kept so existing deployments can be migrated (and rolled back).
            CREATE TABLE IF NOT EXISTS booking_hours (
                weekday   SMALLINT PRIMARY KEY,
                is_open   BOOLEAN  NOT NULL DEFAULT TRUE,
                open_min  SMALLINT NOT NULL DEFAULT 720,
                close_min SMALLINT NOT NULL DEFAULT 1380
            );

            -- bookable time windows per weekday (0 = Monday ... 6 = Sunday),
            -- stored as minutes from midnight. A weekday may have several rows
            -- (e.g. 16:00-17:00 and 19:00-20:00); no rows at all = day off.
            -- close_min may be <= open_min for a window crossing midnight.
            CREATE TABLE IF NOT EXISTS booking_windows (
                id        SERIAL   PRIMARY KEY,
                weekday   SMALLINT NOT NULL,
                open_min  SMALLINT NOT NULL,
                close_min SMALLINT NOT NULL,
                UNIQUE (weekday, open_min, close_min)
            );
            """
        )

        # --- light migrations for existing deployments ---
        await conn.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS blocked BOOLEAN NOT NULL DEFAULT FALSE;"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_activity_tg_created ON activity (tg_id, created_at);"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_activity_created ON activity (created_at);"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bookings_created ON bookings (created_at);"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_booking_windows_weekday ON booking_windows (weekday);"
        )

        # --- seed a starter FAQ once (keeps parity with the old hardcoded list) ---
        count = await conn.fetchval("SELECT COUNT(*) FROM faq")
        if count == 0:
            await conn.executemany(
                """
                INSERT INTO faq (position, question_ru, question_en, answer_ru, answer_en)
                VALUES ($1, $2, $3, $4, $5);
                """,
                [
                    (1, "Парковка", "Parking",
                     "🅿️ Информация о парковке — отредактируйте в панели администратора.",
                     "🅿️ Parking info — please edit this in the admin panel."),
                    (2, "Детское меню", "Kids' menu",
                     "🧒 Информация о детском меню — отредактируйте в панели администратора.",
                     "🧒 Kids' menu info — please edit this in the admin panel."),
                    (3, "Можно ли с животными", "Pets allowed?",
                     "🐾 Информация о животных — отредактируйте в панели администратора.",
                     "🐾 Pets info — please edit this in the admin panel."),
                    (4, "Дресс-код", "Dress code",
                     "👔 Информация о дресс-коде — отредактируйте в панели администратора.",
                     "👔 Dress code info — please edit this in the admin panel."),
                    (5, "Терраса", "Terrace",
                     "🌿 Информация о террасе — отредактируйте в панели администратора.",
                     "🌿 Terrace info — please edit this in the admin panel."),
                ],
            )

        # --- one-time move from booking_hours (one window/day) to booking_windows ---
        migrated = await conn.fetchval(
            "SELECT value FROM settings WHERE key = 'booking_windows_migrated'"
        )
        if migrated != "1":
            legacy = await conn.fetch(
                "SELECT weekday, open_min, close_min FROM booking_hours WHERE is_open"
            )
            if legacy:
                await conn.executemany(
                    """
                    INSERT INTO booking_windows (weekday, open_min, close_min)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (weekday, open_min, close_min) DO NOTHING;
                    """,
                    [(r["weekday"], r["open_min"], r["close_min"]) for r in legacy],
                )
            else:
                # nothing to migrate: fresh install (no legacy rows at all) gets
                # the default window; a deployment where every day was marked as
                # a day off keeps its days off.
                had_legacy = await conn.fetchval("SELECT COUNT(*) FROM booking_hours")
                if not had_legacy:
                    await conn.executemany(
                        """
                        INSERT INTO booking_windows (weekday, open_min, close_min)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (weekday, open_min, close_min) DO NOTHING;
                        """,
                        [(d, _DEFAULT_OPEN_MIN, _DEFAULT_CLOSE_MIN) for d in range(7)],
                    )
            await conn.execute(
                """
                INSERT INTO settings (key, value) VALUES ('booking_windows_migrated', '1')
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
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
                  full_name = EXCLUDED.full_name,
                  blocked = FALSE;
            """,
            tg_id, lang, username, full_name,
        )


async def get_user_lang(tg_id: int) -> str | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT lang FROM users WHERE tg_id = $1", tg_id)
        return row["lang"] if row else None


async def set_user_blocked(tg_id: int, blocked: bool = True) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET blocked = $2 WHERE tg_id = $1", tg_id, blocked
        )


async def list_user_ids(lang: str | None = None) -> list[int]:
    """Non-blocked user ids, optionally filtered by language."""
    async with _pool.acquire() as conn:
        if lang in ("ru", "en"):
            rows = await conn.fetch(
                "SELECT tg_id FROM users WHERE blocked = FALSE AND lang = $1", lang
            )
        else:
            rows = await conn.fetch("SELECT tg_id FROM users WHERE blocked = FALSE")
        return [r["tg_id"] for r in rows]


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


async def get_event(event_id: int) -> asyncpg.Record | None:
    async with _pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM events WHERE id = $1", event_id)


async def list_upcoming_events() -> list[asyncpg.Record]:
    async with _pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT * FROM events
            WHERE event_date >= CURRENT_DATE
            ORDER BY event_date ASC;
            """
        )


async def count_upcoming_events() -> int:
    async with _pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM events WHERE event_date >= CURRENT_DATE"
        )


_EVENT_COLS = {"event_date", "title", "description"}


async def update_event_field(event_id: int, field: str, value) -> None:
    if field not in _EVENT_COLS:
        raise ValueError(f"illegal event field: {field}")
    async with _pool.acquire() as conn:
        await conn.execute(
            f"UPDATE events SET {field} = $2 WHERE id = $1", event_id, value
        )


async def delete_event(event_id: int) -> bool:
    async with _pool.acquire() as conn:
        result = await conn.execute("DELETE FROM events WHERE id = $1", event_id)
        return result.endswith("1")


# --- faq ---
async def list_faq() -> list[asyncpg.Record]:
    async with _pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM faq ORDER BY position ASC, id ASC")


async def get_faq(faq_id: int) -> asyncpg.Record | None:
    async with _pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM faq WHERE id = $1", faq_id)


async def add_faq(question_ru: str, question_en: str, answer_ru: str, answer_en: str) -> int:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO faq (position, question_ru, question_en, answer_ru, answer_en)
            VALUES (
                (SELECT COALESCE(MAX(position), 0) + 1 FROM faq),
                $1, $2, $3, $4
            )
            RETURNING id;
            """,
            question_ru, question_en, answer_ru, answer_en,
        )
        return row["id"]


_FAQ_COLS = {"question_ru", "question_en", "answer_ru", "answer_en"}


async def update_faq_field(faq_id: int, field: str, value: str) -> None:
    if field not in _FAQ_COLS:
        raise ValueError(f"illegal faq field: {field}")
    async with _pool.acquire() as conn:
        await conn.execute(
            f"UPDATE faq SET {field} = $2 WHERE id = $1", faq_id, value
        )


async def delete_faq(faq_id: int) -> bool:
    async with _pool.acquire() as conn:
        result = await conn.execute("DELETE FROM faq WHERE id = $1", faq_id)
        return result.endswith("1")


# --- blocked dates (booking switched off for a specific day) ---
async def list_blocked_dates(upcoming_only: bool = True) -> list[asyncpg.Record]:
    async with _pool.acquire() as conn:
        if upcoming_only:
            return await conn.fetch(
                "SELECT * FROM blocked_dates WHERE day >= CURRENT_DATE ORDER BY day ASC"
            )
        return await conn.fetch("SELECT * FROM blocked_dates ORDER BY day ASC")


async def get_blocked_date(day) -> asyncpg.Record | None:
    async with _pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM blocked_dates WHERE day = $1", day)


async def add_blocked_date(day, message_ru: str | None, message_en: str | None) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO blocked_dates (day, message_ru, message_en)
            VALUES ($1, $2, $3)
            ON CONFLICT (day) DO UPDATE
              SET message_ru = EXCLUDED.message_ru,
                  message_en = EXCLUDED.message_en;
            """,
            day, message_ru, message_en,
        )


async def delete_blocked_date(day) -> bool:
    async with _pool.acquire() as conn:
        result = await conn.execute("DELETE FROM blocked_dates WHERE day = $1", day)
        return result.endswith("1")


async def purge_past_blocked_dates() -> None:
    """Housekeeping: drop days that are already in the past."""
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM blocked_dates WHERE day < CURRENT_DATE")


# --- booking windows (several per weekday, minutes from midnight) ---
async def list_booking_windows() -> list[asyncpg.Record]:
    """Every window, ordered by weekday then start time."""
    async with _pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM booking_windows ORDER BY weekday ASC, open_min ASC"
        )


async def list_day_windows(weekday: int) -> list[asyncpg.Record]:
    """Windows for one weekday, ordered by start time. Empty list = day off."""
    async with _pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM booking_windows WHERE weekday = $1 ORDER BY open_min ASC",
            weekday,
        )


async def get_booking_window(window_id: int) -> asyncpg.Record | None:
    async with _pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM booking_windows WHERE id = $1", window_id
        )


async def add_booking_window(weekday: int, open_min: int, close_min: int) -> int | None:
    """Add a window. Returns None when an identical window already exists."""
    async with _pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO booking_windows (weekday, open_min, close_min)
            VALUES ($1, $2, $3)
            ON CONFLICT (weekday, open_min, close_min) DO NOTHING
            RETURNING id;
            """,
            weekday, open_min, close_min,
        )


async def delete_booking_window(window_id: int) -> bool:
    async with _pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM booking_windows WHERE id = $1", window_id
        )
        return result.endswith("1")


async def clear_day_windows(weekday: int) -> None:
    """Remove every window of a weekday — i.e. make it a day off."""
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM booking_windows WHERE weekday = $1", weekday)


async def replace_day_windows(weekday: int, windows: list[tuple[int, int]]) -> None:
    """Atomically swap all windows of a weekday for a new set."""
    async with _pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM booking_windows WHERE weekday = $1", weekday)
            if windows:
                await conn.executemany(
                    """
                    INSERT INTO booking_windows (weekday, open_min, close_min)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (weekday, open_min, close_min) DO NOTHING;
                    """,
                    [(weekday, o, c) for o, c in windows],
                )


# --- settings (key/value: menu file_id, editable contacts, toggles, ...) ---
async def get_setting(key: str) -> str | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM settings WHERE key = $1", key)
        return row["value"] if row else None


async def set_setting(key: str, value: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO settings (key, value)
            VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
            """,
            key, value,
        )


# --- activity log (used by statistics) ---
async def log_activity(tg_id: int, kind: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO activity (tg_id, kind) VALUES ($1, $2)", tg_id, kind
        )


# --- statistics ---
async def get_user_stats() -> dict:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*)                                                        AS total,
                COUNT(*) FILTER (WHERE created_at >= now() - interval '1 day')  AS new_1d,
                COUNT(*) FILTER (WHERE created_at >= now() - interval '7 days')  AS new_7d,
                COUNT(*) FILTER (WHERE created_at >= now() - interval '30 days') AS new_30d,
                COUNT(*) FILTER (WHERE lang = 'ru')                             AS ru,
                COUNT(*) FILTER (WHERE lang = 'en')                             AS en,
                COUNT(*) FILTER (WHERE blocked)                                 AS blocked
            FROM users;
            """
        )
        return dict(row)


async def get_active_users() -> dict:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(DISTINCT tg_id) FILTER (WHERE created_at >= now() - interval '1 day')  AS active_1d,
                COUNT(DISTINCT tg_id) FILTER (WHERE created_at >= now() - interval '7 days')  AS active_7d,
                COUNT(DISTINCT tg_id) FILTER (WHERE created_at >= now() - interval '30 days') AS active_30d
            FROM activity;
            """
        )
        return dict(row)


async def get_booking_stats() -> dict:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*)                                             AS total,
                COUNT(*) FILTER (WHERE status = 'pending')           AS pending,
                COUNT(*) FILTER (WHERE status = 'confirmed')         AS confirmed,
                COUNT(*) FILTER (WHERE status = 'declined')          AS declined,
                COUNT(*) FILTER (WHERE status = 'reschedule_offered') AS reschedule_offered,
                COUNT(*) FILTER (WHERE status = 'cancelled')         AS cancelled,
                COUNT(*) FILTER (WHERE created_at >= now() - interval '1 day')  AS d1,
                COUNT(*) FILTER (WHERE created_at >= now() - interval '7 days')  AS d7,
                COUNT(*) FILTER (WHERE created_at >= now() - interval '30 days') AS d30
            FROM bookings;
            """
        )
        return dict(row)


async def top_booking_times(limit: int = 5) -> list[asyncpg.Record]:
    async with _pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT b_time AS v, COUNT(*) AS c
            FROM bookings
            GROUP BY b_time
            ORDER BY c DESC, v ASC
            LIMIT $1;
            """,
            limit,
        )


async def top_booking_dates(limit: int = 5) -> list[asyncpg.Record]:
    async with _pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT b_date AS v, COUNT(*) AS c
            FROM bookings
            GROUP BY b_date
            ORDER BY c DESC, v ASC
            LIMIT $1;
            """,
            limit,
        )


async def get_activity_stats() -> dict:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*)                                     AS total,
                COUNT(*) FILTER (WHERE kind = 'message')     AS messages,
                COUNT(*) FILTER (WHERE kind = 'callback')    AS callbacks,
                COUNT(*) FILTER (WHERE created_at >= now() - interval '1 day')  AS d1,
                COUNT(*) FILTER (WHERE created_at >= now() - interval '7 days')  AS d7
            FROM activity;
            """
        )
        return dict(row)


async def get_session_stats(gap_minutes: int = 15) -> dict:
    """Group each user's activity into sessions (split on gaps > gap_minutes)
    and return session count, total and average duration in seconds."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            WITH ordered AS (
                SELECT tg_id, created_at,
                       LAG(created_at) OVER (PARTITION BY tg_id ORDER BY created_at) AS prev
                FROM activity
            ),
            marked AS (
                SELECT tg_id, created_at,
                       CASE WHEN prev IS NULL
                                 OR created_at - prev > make_interval(mins => $1)
                            THEN 1 ELSE 0 END AS new_session
                FROM ordered
            ),
            sessioned AS (
                SELECT tg_id, created_at,
                       SUM(new_session) OVER (PARTITION BY tg_id ORDER BY created_at
                                              ROWS UNBOUNDED PRECEDING) AS sess
                FROM marked
            ),
            sessions AS (
                SELECT tg_id, sess,
                       EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at))) AS dur
                FROM sessioned
                GROUP BY tg_id, sess
            )
            SELECT
                COUNT(*)                     AS session_count,
                COALESCE(SUM(dur), 0)        AS total_seconds,
                COALESCE(AVG(dur), 0)        AS avg_seconds
            FROM sessions;
            """,
            gap_minutes,
        )
        return dict(row)
