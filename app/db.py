from __future__ import annotations

import logging
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
    creator_id BIGINT NOT NULL REFERENCES bot_users(user_id) ON DELETE CASCADE,
    place TEXT NOT NULL,
    meetup_date DATE NOT NULL,
    meetup_time TIME NOT NULL,
    max_people INTEGER NOT NULL CHECK (max_people >= 2 AND max_people <= 100),
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS meetup_members (
    meetup_id BIGINT NOT NULL REFERENCES meetups(meetup_id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES bot_users(user_id) ON DELETE CASCADE,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (meetup_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_meetups_active
ON meetups(is_active, meetup_date);

CREATE INDEX IF NOT EXISTS idx_meetup_members
ON meetup_members(meetup_id);
"""


class Storage(Protocol):
    async def open(self) -> None: ...
    async def close(self) -> None: ...

    async def track_user(
        self,
        user_id: int,
        username: str | None,
    ) -> None: ...

    async def create_meetup(
        self,
        creator_id: int,
        place: str,
        meetup_date,
        meetup_time,
        max_people: int,
        description: str,
    ) -> int: ...

    async def get_meetup(self, meetup_id: int): ...

    async def get_active_meetups(self): ...

    async def join_meetup(
        self,
        meetup_id: int,
        user_id: int,
    ) -> tuple[bool, str]: ...

    async def get_meetup_members(self, meetup_id: int): ...

    async def get_user_meetups(self, user_id: int): ...

    async def close_expired_meetups(self) -> None: ...

    async def user_count(self) -> int: ...

    @property
    def backend(self) -> str: ...


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

        logger.info("storage.open backend=postgres")

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()

    async def track_user(
        self,
        user_id: int,
        username: str | None,
    ) -> None:
        assert self._pool is not None

        await self._pool.execute(
            """
            INSERT INTO bot_users (user_id, username)
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
        place: str,
        meetup_date,
        meetup_time,
        max_people: int,
        description: str,
    ) -> int:
        assert self._pool is not None

        meetup_id = await self._pool.fetchval(
            """
            INSERT INTO meetups (
                creator_id,
                place,
                meetup_date,
                meetup_time,
                max_people,
                description,
                expires_at
            )
            VALUES (
                $1,
                $2,
                $3,
                $4,
                $5,
                $6,
                (($3 + $4) + interval '24 hours')
            )
            RETURNING meetup_id
            """,
            creator_id,
            place,
            meetup_date,
            meetup_time,
            max_people,
            description,
        )

        await self._pool.execute(
            """
            INSERT INTO meetup_members (meetup_id, user_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
            """,
            meetup_id,
            creator_id,
        )

        return int(meetup_id)

    async def get_meetup(self, meetup_id: int):
        assert self._pool is not None

        return await self._pool.fetchrow(
            """
            SELECT
                m.*,
                COUNT(mm.user_id)::int AS member_count
            FROM meetups m
            LEFT JOIN meetup_members mm
                ON mm.meetup_id = m.meetup_id
            WHERE m.meetup_id = $1
              AND m.is_active = TRUE
              AND m.expires_at > now()
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
                COUNT(mm.user_id)::int AS member_count
            FROM meetups m
            LEFT JOIN meetup_members mm
                ON mm.meetup_id = m.meetup_id
            WHERE m.is_active = TRUE
              AND m.expires_at > now()
            GROUP BY m.meetup_id
            ORDER BY m.meetup_date, m.meetup_time
            LIMIT 50
            """
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
                    SELECT
                        m.*,
                        COUNT(mm.user_id)::int AS member_count
                    FROM meetups m
                    LEFT JOIN meetup_members mm
                        ON mm.meetup_id = m.meetup_id
                    WHERE m.meetup_id = $1
                      AND m.is_active = TRUE
                      AND m.expires_at > now()
                    GROUP BY m.meetup_id
                    FOR UPDATE
                    """,
                    meetup_id,
                )

                if not meetup:
                    return False, "Сходка уже недоступна."

                if meetup["member_count"] >= meetup["max_people"]:
                    return False, "В этой сходке уже нет свободных мест."

                exists = await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM meetup_members
                        WHERE meetup_id = $1
                          AND user_id = $2
                    )
                    """,
                    meetup_id,
                    user_id,
                )

                if exists:
                    return False, "Ты уже участвуешь в этой сходке."

                await conn.execute(
                    """
                    INSERT INTO meetup_members (meetup_id, user_id)
                    VALUES ($1, $2)
                    """,
                    meetup_id,
                    user_id,
                )

                return True, "Ты присоединился к сходке."

    async def get_meetup_members(self, meetup_id: int):
        assert self._pool is not None

        return await self._pool.fetch(
            """
            SELECT
                u.user_id,
                u.username,
                mm.joined_at
            FROM meetup_members mm
            JOIN bot_users u
                ON u.user_id = mm.user_id
            WHERE mm.meetup_id = $1
            ORDER BY mm.joined_at
            """,
            meetup_id,
        )

    async def get_user_meetups(self, user_id: int):
        assert self._pool is not None

        return await self._pool.fetch(
            """
            SELECT
                m.*,
                COUNT(mm.user_id)::int AS member_count
            FROM meetups m
            JOIN meetup_members mine
                ON mine.meetup_id = m.meetup_id
               AND mine.user_id = $1
            LEFT JOIN meetup_members mm
                ON mm.meetup_id = m.meetup_id
            WHERE m.is_active = TRUE
              AND m.expires_at > now()
            GROUP BY m.meetup_id
            ORDER BY m.meetup_date, m.meetup_time
            """,
            user_id,
        )

    async def close_expired_meetups(self) -> None:
        assert self._pool is not None

        await self._pool.execute(
            """
            UPDATE meetups
            SET is_active = FALSE
            WHERE is_active = TRUE
              AND expires_at <= now()
            """
        )

    async def user_count(self) -> int:
        assert self._pool is not None

        return int(
            await self._pool.fetchval(
                "SELECT count(*) FROM bot_users"
            )
        )


def create_storage(
    database_url: str | None,
) -> Storage:
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL не задан. "
            "Для сходок нужен PostgreSQL."
        )

    return PostgresStorage(database_url)
    
