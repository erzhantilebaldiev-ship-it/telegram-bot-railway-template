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
    creator_id BIGINT NOT NULL
        REFERENCES bot_users(user_id)
        ON DELETE CASCADE,

    title TEXT NOT NULL,
    city TEXT NOT NULL,
    place TEXT NOT NULL,
    meetup_date DATE NOT NULL,
    meetup_time TIME NOT NULL,

    description TEXT NOT NULL DEFAULT '',
    max_people INTEGER NOT NULL,

    group_chat_id BIGINT,
    group_message_id BIGINT,

    status TEXT NOT NULL DEFAULT 'open',

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ends_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS meetup_members (
    meetup_id BIGINT NOT NULL
        REFERENCES meetups(meetup_id)
        ON DELETE CASCADE,

    user_id BIGINT NOT NULL
        REFERENCES bot_users(user_id)
        ON DELETE CASCADE,

    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (meetup_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_meetups_status
ON meetups(status);

CREATE INDEX IF NOT EXISTS idx_meetups_date
ON meetups(meetup_date);

CREATE INDEX IF NOT EXISTS idx_meetup_members_meetup
ON meetup_members(meetup_id);

CREATE INDEX IF NOT EXISTS idx_meetup_members_user
ON meetup_members(user_id);
"""


class Storage(Protocol):

    async def open(self) -> None:
        ...

    async def close(self) -> None:
        ...

    @property
    def backend(self) -> str:
        ...

    async def track_user(
        self,
        user_id: int,
        username: str | None,
    ) -> None:
        ...

    async def get_user(
        self,
        user_id: int,
    ):
        ...

    async def create_meetup(
        self,
        creator_id: int,
        title: str,
        city: str,
        place: str,
        meetup_date,
        meetup_time,
        description: str,
        max_people: int,
        ends_at,
    ) -> int:
        ...

    async def get_meetup(
        self,
        meetup_id: int,
    ):
        ...

    async def get_open_meetups(
        self,
        limit: int = 20,
    ):
        ...

    async def get_my_meetups(
        self,
        creator_id: int,
        limit: int = 20,
    ):
        ...

    async def join_meetup(
        self,
        meetup_id: int,
        user_id: int,
    ) -> bool:
        ...

    async def leave_meetup(
        self,
        meetup_id: int,
        user_id: int,
    ) -> bool:
        ...

    async def is_member(
        self,
        meetup_id: int,
        user_id: int,
    ) -> bool:
        ...

    async def get_members(
        self,
        meetup_id: int,
    ):
        ...

    async def get_member_count(
        self,
        meetup_id: int,
    ) -> int:
        ...

    async def set_group(
        self,
        meetup_id: int,
        group_chat_id: int,
    ) -> None:
        ...

    async def close_meetup(
        self,
        meetup_id: int,
    ) -> None:
        ...

    async def get_expired_meetups(self):
        ...

    async def remove_all_members(
        self,
        meetup_id: int,
        creator_id: int,
    ) -> None:
        ...

    async def user_count(self) -> int:
        ...


class MemoryStorage:

    def __init__(self) -> None:
        self._users: dict[int, str | None] = {}
        self._meetups: dict[int, dict] = {}
        self._members: dict[int, set[int]] = {}
        self._next_meetup_id = 1

    @property
    def backend(self) -> str:
        return "memory"

    async def open(self) -> None:
        logger.info("storage.open backend=memory")

    async def close(self) -> None:
        return None

    async def track_user(
        self,
        user_id: int,
        username: str | None,
    ) -> None:
        self._users[user_id] = username

    async def get_user(
        self,
        user_id: int,
    ):
        if user_id not in self._users:
            return None

        return {
            "user_id": user_id,
            "username": self._users[user_id],
        }

    async def create_meetup(
        self,
        creator_id: int,
        title: str,
        city: str,
        place: str,
        meetup_date,
        meetup_time,
        description: str,
        max_people: int,
        ends_at,
    ) -> int:

        meetup_id = self._next_meetup_id
        self._next_meetup_id += 1

        self._meetups[meetup_id] = {
            "meetup_id": meetup_id,
            "creator_id": creator_id,
            "title": title,
            "city": city,
            "place": place,
            "meetup_date": meetup_date,
            "meetup_time": meetup_time,
            "description": description,
            "max_people": max_people,
            "group_chat_id": None,
            "status": "open",
            "ends_at": ends_at,
        }

        self._members[meetup_id] = {
            creator_id
        }

        return meetup_id

    async def get_meetup(
        self,
        meetup_id: int,
    ):
        meetup = self._meetups.get(meetup_id)

        if not meetup:
            return None

        data = dict(meetup)
        data["member_count"] = len(
            self._members.get(meetup_id, set())
        )

        return data

    async def get_open_meetups(
        self,
        limit: int = 20,
    ):
        result = []

        for meetup in self._meetups.values():

            if meetup["status"] != "open":
                continue

            data = dict(meetup)

            data["member_count"] = len(
                self._members.get(
                    meetup["meetup_id"],
                    set(),
                )
            )

            result.append(data)

        result.sort(
            key=lambda x: (
                x["meetup_date"],
                x["meetup_time"],
            )
        )

        return result[:limit]

    async def get_my_meetups(
        self,
        creator_id: int,
        limit: int = 20,
    ):
        result = []

        for meetup in self._meetups.values():

            if meetup["creator_id"] != creator_id:
                continue

            data = dict(meetup)

            data["member_count"] = len(
                self._members.get(
                    meetup["meetup_id"],
                    set(),
                )
            )

            result.append(data)

        result.sort(
            key=lambda x: (
                x["meetup_date"],
                x["meetup_time"],
            ),
            reverse=True,
        )

        return result[:limit]

    async def join_meetup(
        self,
        meetup_id: int,
        user_id: int,
    ) -> bool:

        meetup = self._meetups.get(
            meetup_id
        )

        if not meetup:
            return False

        if meetup["status"] != "open":
            return False

        members = self._members.setdefault(
            meetup_id,
            set(),
        )

        if user_id in members:
            return False

        if len(members) >= meetup["max_people"]:
            return False

        members.add(user_id)

        return True

    async def leave_meetup(
        self,
        meetup_id: int,
        user_id: int,
    ) -> bool:

        meetup = self._meetups.get(
            meetup_id
        )

        if not meetup:
            return False

        if user_id == meetup["creator_id"]:
            return False

        members = self._members.get(
            meetup_id,
            set(),
        )

        if user_id not in members:
            return False

        members.remove(user_id)

        return True

    async def is_member(
        self,
        meetup_id: int,
        user_id: int,
    ) -> bool:

        return user_id in self._members.get(
            meetup_id,
            set(),
        )

    async def get_members(
        self,
        meetup_id: int,
    ):
        result = []

        for user_id in self._members.get(
            meetup_id,
            set(),
        ):
            result.append(
                {
                    "user_id": user_id,
                    "username": self._users.get(
                        user_id
                    ),
                }
            )

        return result

    async def get_member_count(
        self,
        meetup_id: int,
    ) -> int:

        return len(
            self._members.get(
                meetup_id,
                set(),
            )
        )

    async def set_group(
        self,
        meetup_id: int,
        group_chat_id: int,
    ) -> None:

        if meetup_id in self._meetups:
            self._meetups[
                meetup_id
            ]["group_chat_id"] = group_chat_id

    async def close_meetup(
        self,
        meetup_id: int,
    ) -> None:

        if meetup_id in self._meetups:
            self._meetups[
                meetup_id
            ]["status"] = "closed"

    async def get_expired_meetups(self):
        return []

    async def remove_all_members(
        self,
        meetup_id: int,
        creator_id: int,
    ) -> None:

        self._members[meetup_id] = {
            creator_id
        }

    async def user_count(self) -> int:
        return len(self._users)


class PostgresStorage:

    def __init__(
        self,
        dsn: str,
    ) -> None:

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

        logger.info(
            "storage.open backend=postgres"
        )

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
            INSERT INTO bot_users
            (user_id, username)
            VALUES ($1, $2)

            ON CONFLICT (user_id)
            DO UPDATE SET
                username = EXCLUDED.username,
                last_seen = now()
            """,
            user_id,
            username,
        )

    async def get_user(
        self,
        user_id: int,
    ):

        assert self._pool is not None

        return await self._pool.fetchrow(
            """
            SELECT
                user_id,
                username
            FROM bot_users
            WHERE user_id = $1
            """,
            user_id,
        )

    async def create_meetup(
        self,
        creator_id: int,
        title: str,
        city: str,
        place: str,
        meetup_date,
        meetup_time,
        description: str,
        max_people: int,
        ends_at,
    ) -> int:

        assert self._pool is not None

        async with self._pool.acquire() as conn:

            async with conn.transaction():

                meetup_id = await conn.fetchval(
                    """
                    INSERT INTO meetups
                    (
                        creator_id,
                        title,
                        city,
                        place,
                        meetup_date,
                        meetup_time,
                        description,
                        max_people,
                        ends_at
                    )
                    VALUES
                    (
                        $1,$2,$3,$4,$5,
                        $6,$7,$8,$9
                    )
                    RETURNING meetup_id
                    """,
                    creator_id,
                    title,
                    city,
                    place,
                    meetup_date,
                    meetup_time,
                    description,
                    max_people,
                    ends_at,
                )

                await conn.execute(
                    """
                    INSERT INTO meetup_members
                    (
                        meetup_id,
                        user_id
                    )
                    VALUES ($1,$2)
                    """,
                    meetup_id,
                    creator_id,
                )

                return int(meetup_id)

    async def get_meetup(
        self,
        meetup_id: int,
    ):

        assert self._pool is not None

        return await self._pool.fetchrow(
            """
            SELECT
                m.*,
                COUNT(mm.user_id)::int
                    AS member_count
            FROM meetups m
            LEFT JOIN meetup_members mm
                ON mm.meetup_id = m.meetup_id
            WHERE m.meetup_id = $1
            GROUP BY m.meetup_id
            """,
            meetup_id,
        )

    async def get_open_meetups(
        self,
        limit: int = 20,
    ):

        assert self._pool is not None

        return await self._pool.fetch(
            """
            SELECT
                m.*,
                COUNT(mm.user_id)::int
                    AS member_count
            FROM meetups m
            LEFT JOIN meetup_members mm
                ON mm.meetup_id = m.meetup_id
            WHERE m.status = 'open'
            GROUP BY m.meetup_id
            ORDER BY
                m.meetup_date,
                m.meetup_time
            LIMIT $1
            """,
            limit,
        )

    async def get_my_meetups(
        self,
        creator_id: int,
        limit: int = 20,
    ):

        assert self._pool is not None

        return await self._pool.fetch(
            """
            SELECT
                m.*,
                COUNT(mm.user_id)::int
                    AS member_count
            FROM meetups m
            LEFT JOIN meetup_members mm
                ON mm.meetup_id = m.meetup_id
            WHERE m.creator_id = $1
            GROUP BY m.meetup_id
            ORDER BY m.created_at DESC
            LIMIT $2
            """,
            creator_id,
            limit,
        )

    async def join_meetup(
        self,
        meetup_id: int,
        user_id: int,
    ) -> bool:

        assert self._pool is not None

        async with self._pool.acquire() as conn:

            async with conn.transaction():

                meetup = await conn.fetchrow(
                    """
                    SELECT
                        status,
                        max_people
                    FROM meetups
                    WHERE meetup_id = $1
                    FOR UPDATE
                    """,
                    meetup_id,
                )

                if not meetup:
                    return False

                if meetup["status"] != "open":
                    return False

                count = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM meetup_members
                    WHERE meetup_id = $1
                    """,
                    meetup_id,
                )

                if count >= meetup["max_people"]:
                    return False

                result = await conn.execute(
                    """
                    INSERT INTO meetup_members
                    (
                        meetup_id,
                        user_id
                    )
                    VALUES ($1,$2)
                    ON CONFLICT DO NOTHING
                    """,
                    meetup_id,
                    user_id,
                )

                return result == "INSERT 0 1"

    async def leave_meetup(
        self,
        meetup_id: int,
        user_id: int,
    ) -> bool:

        assert self._pool is not None

        creator_id = await self._pool.fetchval(
            """
            SELECT creator_id
            FROM meetups
            WHERE meetup_id = $1
            """,
            meetup_id,
        )

        if creator_id == user_id:
            return False

        result = await self._pool.execute(
            """
            DELETE FROM meetup_members
            WHERE meetup_id = $1
              AND user_id = $2
            """,
            meetup_id,
            user_id,
        )

        return result == "DELETE 1"

    async def is_member(
        self,
        meetup_id: int,
        user_id: int,
    ) -> bool:

        assert self._pool is not None

        return bool(
            await self._pool.fetchval(
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
        )

    async def get_members(
        self,
        meetup_id: int,
    ):

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

    async def get_member_count(
        self,
        meetup_id: int,
    ) -> int:

        assert self._pool is not None

        return int(
            await self._pool.fetchval(
                """
                SELECT COUNT(*)
                FROM meetup_members
                WHERE meetup_id = $1
                """,
                meetup_id,
            )
        )

    async def set_group(
        self,
        meetup_id: int,
        group_chat_id: int,
    ) -> None:

        assert self._pool is not None

        await self._pool.execute(
            """
            UPDATE meetups
            SET group_chat_id = $2
            WHERE meetup_id = $1
            """,
            meetup_id,
            group_chat_id,
        )

    async def close_meetup(
        self,
        meetup_id: int,
    ) -> None:

        assert self._pool is not None

        await self._pool.execute(
            """
            UPDATE meetups
            SET
                status = 'closed',
                closed_at = now()
            WHERE meetup_id = $1
            """,
            meetup_id,
        )

    async def get_expired_meetups(self):

        assert self._pool is not None

        return await self._pool.fetch(
            """
            SELECT *
            FROM meetups
            WHERE status = 'open'
              AND ends_at IS NOT NULL
              AND ends_at <= now()
            ORDER BY ends_at
            """
        )

    async def remove_all_members(
        self,
        meetup_id: int,
        creator_id: int,
    ) -> None:

        assert self._pool is not None

        await self._pool.execute(
            """
            DELETE FROM meetup_members
            WHERE meetup_id = $1
              AND user_id != $2
            """,
            meetup_id,
            creator_id,
        )

    async def user_count(self) -> int:

        assert self._pool is not None

        return int(
            await self._pool.fetchval(
                """
                SELECT COUNT(*)
                FROM bot_users
                """
            )
        )


def create_storage(
    database_url: str | None,
) -> Storage:

    if database_url:
        return PostgresStorage(
            database_url
        )

    return MemoryStorage()
