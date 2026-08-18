from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Protocol

import asyncpg

logger = logging.getLogger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS bot_users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS meetups (
    meetup_id BIGSERIAL PRIMARY KEY,

    creator_id BIGINT NOT NULL
        REFERENCES bot_users(user_id)
        ON DELETE CASCADE,

    title TEXT NOT NULL,
    place TEXT NOT NULL,

    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    cleanup_at TIMESTAMPTZ NOT NULL,

    description TEXT NOT NULL DEFAULT '',

    max_participants INTEGER NOT NULL
        CHECK (max_participants >= 1 AND max_participants <= 100),

    telegram_chat_id BIGINT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    active BOOLEAN NOT NULL DEFAULT TRUE,
    cleaned BOOLEAN NOT NULL DEFAULT FALSE,

    CHECK (ends_at > starts_at),
    CHECK (cleanup_at > ends_at)
);

CREATE TABLE IF NOT EXISTS meetup_participants (
    meetup_id BIGINT NOT NULL
        REFERENCES meetups(meetup_id)
        ON DELETE CASCADE,

    user_id BIGINT NOT NULL
        REFERENCES bot_users(user_id)
        ON DELETE CASCADE,

    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (meetup_id, user_id)
);

CREATE TABLE IF NOT EXISTS meetup_groups (
    chat_id BIGINT PRIMARY KEY,

    title TEXT,

    meetup_id BIGINT
        REFERENCES meetups(meetup_id)
        ON DELETE SET NULL,

    active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_meetups_cleanup
ON meetups(cleanup_at);

CREATE INDEX IF NOT EXISTS idx_meetups_active
ON meetups(active);

CREATE INDEX IF NOT EXISTS idx_participants_meetup
ON meetup_participants(meetup_id);

CREATE INDEX IF NOT EXISTS idx_groups_meetup
ON meetup_groups(meetup_id);
"""


class Storage(Protocol):
    @property
    def backend(self) -> str:
        ...

    async def open(self) -> None:
        ...

    async def close(self) -> None:
        ...

    async def track_user(
        self,
        user_id: int,
        username: str | None,
    ) -> None:
        ...

    async def create_meetup(
        self,
        creator_id: int,
        title: str,
        place: str,
        starts_at: datetime,
        ends_at: datetime,
        description: str,
        max_participants: int,
    ) -> int:
        ...

    async def get_meetup(self, meetup_id: int):
        ...

    async def get_active_meetups(self):
        ...

    async def get_my_meetups(self, user_id: int):
        ...

    async def join_meetup(
        self,
        meetup_id: int,
        user_id: int,
    ) -> tuple[bool, str]:
        ...

    async def leave_meetup(
        self,
        meetup_id: int,
        user_id: int,
    ) -> bool:
        ...

    async def is_participant(
        self,
        meetup_id: int,
        user_id: int,
    ) -> bool:
        ...

    async def get_participants(self, meetup_id: int):
        ...

    async def participant_count(self, meetup_id: int) -> int:
        ...

    async def get_meetups_ready_for_cleanup(self):
        ...

    async def mark_meetup_cleaned(self, meetup_id: int) -> bool:
        ...

    async def cleanup_finished_meetups(self) -> int:
        ...

    async def register_group(
        self,
        chat_id: int,
        title: str | None = None,
    ) -> None:
        ...

    async def get_free_group(self):
        ...

    async def assign_group(
        self,
        meetup_id: int,
        chat_id: int,
    ) -> bool:
        ...

    async def get_meetup_by_chat_id(self, chat_id: int):
        ...

    async def get_group_chat_id(self, meetup_id: int):
        ...


class PostgresStorage:

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    @property
    def backend(self) -> str:
        return "postgres"

    async def open(self) -> None:
        self._pool = await asyncpg.create_pool(
            self._dsn,
            min_size=1,
            max_size=5,
        )

        async with self._pool.acquire() as conn:
            await conn.execute(_SCHEMA)

        logger.info("PostgreSQL storage opened")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def track_user(
        self,
        user_id: int,
        username: str | None,
    ) -> None:
        assert self._pool is not None

        await self._pool.execute(
            """
            INSERT INTO bot_users (
                user_id,
                username
            )
            VALUES ($1, $2)
            ON CONFLICT (user_id)
            DO UPDATE SET
                username = EXCLUDED.username,
                last_seen = now()
            """,
            user_id,
            username,
        )

    async def create_meetup(
        self,
        creator_id: int,
        title: str,
        place: str,
        starts_at: datetime,
        ends_at: datetime,
        description: str,
        max_participants: int,
    ) -> int:
        assert self._pool is not None

        cleanup_at = ends_at + timedelta(hours=24)

        async with self._pool.acquire() as conn:
            meetup_id = await conn.fetchval(
                """
                INSERT INTO meetups (
                    creator_id,
                    title,
                    place,
                    starts_at,
                    ends_at,
                    cleanup_at,
                    description,
                    max_participants
                )
                VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8
                )
                RETURNING meetup_id
                """,
                creator_id,
                title,
                place,
                starts_at,
                ends_at,
                cleanup_at,
                description,
                max_participants,
            )

        return int(meetup_id)

    async def get_meetup(self, meetup_id: int):
        assert self._pool is not None

        return await self._pool.fetchrow(
            """
            SELECT
                m.*,
                COUNT(mp.user_id)::int AS participant_count
            FROM meetups m
            LEFT JOIN meetup_participants mp
                ON mp.meetup_id = m.meetup_id
            WHERE m.meetup_id = $1
              AND m.cleaned = FALSE
            GROUP BY m.meetup_id
            """,
            meetup_id,
        )

    async def get_active_meetups(self):
        assert self._pool is not None

        return await self._pool.fetch(
            """
            SELECT
                m.*,
                COUNT(mp.user_id)::int AS participant_count
            FROM meetups m
            LEFT JOIN meetup_participants mp
                ON mp.meetup_id = m.meetup_id
            WHERE m.active = TRUE
              AND m.cleaned = FALSE
              AND m.cleanup_at > now()
            GROUP BY m.meetup_id
            ORDER BY m.starts_at
            """
        )

    async def get_my_meetups(
        self,
        user_id: int,
    ):
        assert self._pool is not None

        return await self._pool.fetch(
            """
            SELECT
                m.*,
                COUNT(mp2.user_id)::int AS participant_count
            FROM meetups m
            JOIN meetup_participants mp
                ON mp.meetup_id = m.meetup_id
               AND mp.user_id = $1
            LEFT JOIN meetup_participants mp2
                ON mp2.meetup_id = m.meetup_id
            WHERE m.active = TRUE
              AND m.cleaned = FALSE
            GROUP BY m.meetup_id
            ORDER BY m.starts_at
            """,
            user_id,
        )

    async def join_meetup(
        self,
        meetup_id: int,
        user_id: int,
    ) -> tuple[bool, str]:
        assert self._pool is not None

        async with self._pool.acquire() as conn:
            async with conn.transaction():

                meetup = await conn.fetchrow(
                    """
                    SELECT *
                    FROM meetups
                    WHERE meetup_id = $1
                      AND active = TRUE
                      AND cleaned = FALSE
                    FOR UPDATE
                    """,
                    meetup_id,
                )

                if not meetup:
                    return False, "not_found"

                now = datetime.now(timezone.utc)

                if meetup["cleanup_at"] <= now:
                    return False, "expired"

                exists = await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM meetup_participants
                        WHERE meetup_id = $1
                          AND user_id = $2
                    )
                    """,
                    meetup_id,
                    user_id,
                )

                if exists:
                    return False, "already_joined"

                count = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM meetup_participants
                    WHERE meetup_id = $1
                    """,
                    meetup_id,
                )

                if count >= meetup["max_participants"]:
                    return False, "full"

                await conn.execute(
                    """
                    INSERT INTO meetup_participants (
                        meetup_id,
                        user_id
                    )
                    VALUES ($1,$2)
                    """,
                    meetup_id,
                    user_id,
                )

        return True, "joined"

    async def leave_meetup(
        self,
        meetup_id: int,
        user_id: int,
    ) -> bool:
        assert self._pool is not None

        result = await self._pool.execute(
            """
            DELETE FROM meetup_participants
            WHERE meetup_id = $1
              AND user_id = $2
            """,
            meetup_id,
            user_id,
        )

        return result.endswith("1")

    async def is_participant(
        self,
        meetup_id: int,
        user_id: int,
    ) -> bool:
        assert self._pool is not None

        result = await self._pool.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM meetup_participants
                WHERE meetup_id = $1
                  AND user_id = $2
            )
            """,
            meetup_id,
            user_id,
        )

        return bool(result)

    async def get_participants(
        self,
        meetup_id: int,
    ):
        assert self._pool is not None

        return await self._pool.fetch(
            """
            SELECT
                u.user_id,
                u.username,
                mp.joined_at
            FROM meetup_participants mp
            JOIN bot_users u
                ON u.user_id = mp.user_id
            WHERE mp.meetup_id = $1
            ORDER BY mp.joined_at
            """,
            meetup_id,
        )

    async def participant_count(
        self,
        meetup_id: int,
    ) -> int:
        assert self._pool is not None

        result = await self._pool.fetchval(
            """
            SELECT COUNT(*)
            FROM meetup_participants
            WHERE meetup_id = $1
            """,
            meetup_id,
        )

        return int(result or 0)

    async def get_meetups_ready_for_cleanup(self):
        assert self._pool is not None

        return await self._pool.fetch(
            """
            SELECT *
            FROM meetups
            WHERE cleaned = FALSE
              AND cleanup_at <= now()
            ORDER BY cleanup_at
            """
        )

    async def mark_meetup_cleaned(
        self,
        meetup_id: int,
    ) -> bool:
        assert self._pool is not None

        async with self._pool.acquire() as conn:
            async with conn.transaction():

                meetup = await conn.fetchrow(
                    """
                    SELECT telegram_chat_id
                    FROM meetups
                    WHERE meetup_id = $1
                      AND cleaned = FALSE
                    FOR UPDATE
                    """,
                    meetup_id,
                )

                if not meetup:
                    return False

                await conn.execute(
                    """
                    DELETE FROM meetup_participants
                    WHERE meetup_id = $1
                    """,
                    meetup_id,
                )

                await conn.execute(
                    """
                    UPDATE meetup_groups
                    SET meetup_id = NULL
                    WHERE meetup_id = $1
                    """,
                    meetup_id,
                )

                result = await conn.execute(
                    """
                    UPDATE meetups
                    SET
                        active = FALSE,
                        cleaned = TRUE
                    WHERE meetup_id = $1
                      AND cleaned = FALSE
                    """,
                    meetup_id,
                )

        return result.endswith("1")

    async def cleanup_finished_meetups(self) -> int:
        meetups = await self.get_meetups_ready_for_cleanup()

        cleaned = 0

        for meetup in meetups:
            if await self.mark_meetup_cleaned(
                meetup["meetup_id"]
            ):
                cleaned += 1

        return cleaned

    # --------------------------------------------------
    # ПОСТОЯННЫЕ TELEGRAM-ГРУППЫ
    # --------------------------------------------------

    async def register_group(
        self,
        chat_id: int,
        title: str | None = None,
    ) -> None:
        assert self._pool is not None

        await self._pool.execute(
            """
            INSERT INTO meetup_groups (
                chat_id,
                title
            )
            VALUES ($1,$2)
            ON CONFLICT (chat_id)
            DO UPDATE SET
                title = EXCLUDED.title
            """,
            chat_id,
            title,
        )

    async def get_free_group(self):
        assert self._pool is not None

        return await self._pool.fetchrow(
            """
            SELECT *
            FROM meetup_groups
            WHERE active = TRUE
              AND meetup_id IS NULL
            ORDER BY created_at
            LIMIT 1
            """
        )

    async def assign_group(
        self,
        meetup_id: int,
        chat_id: int,
    ) -> bool:
        assert self._pool is not None

        async with self._pool.acquire() as conn:
            async with conn.transaction():

                group = await conn.fetchrow(
                    """
                    SELECT *
                    FROM meetup_groups
                    WHERE chat_id = $1
                      AND active = TRUE
                      AND meetup_id IS NULL
                    FOR UPDATE
                    """,
                    chat_id,
                )

                if not group:
                    return False

                result = await conn.execute(
                    """
                    UPDATE meetup_groups
                    SET meetup_id = $1
                    WHERE chat_id = $2
                      AND meetup_id IS NULL
                    """,
                    meetup_id,
                    chat_id,
                )

                if not result.endswith("1"):
                    return False

                await conn.execute(
                    """
                    UPDATE meetups
                    SET telegram_chat_id = $2
                    WHERE meetup_id = $1
                    """,
                    meetup_id,
                    chat_id,
                )

        return True

    async def get_meetup_by_chat_id(
        self,
        chat_id: int,
    ):
        assert self._pool is not None

        return await self._pool.fetchrow(
            """
            SELECT *
            FROM meetups
            WHERE telegram_chat_id = $1
              AND cleaned = FALSE
            """,
            chat_id,
        )

    async def get_group_chat_id(
        self,
        meetup_id: int,
    ):
        assert self._pool is not None

        return await self._pool.fetchval(
            """
            SELECT telegram_chat_id
            FROM meetups
            WHERE meetup_id = $1
            """,
            meetup_id,
        )


def create_storage(
    database_url: str | None,
) -> Storage:
    if database_url:
        return PostgresStorage(database_url)

    raise RuntimeError(
        "DATABASE_URL is not configured. "
        "PostgreSQL is required for meetup groups."
    )
