from future import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Protocol

import asyncpg

logger = logging.getLogger(name)

_SCHEMA = “””
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
description TEXT NOT NULL DEFAULT '',
max_participants INTEGER NOT NULL
    CHECK (max_participants >= 1 AND max_participants <= 100),
created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
active BOOLEAN NOT NULL DEFAULT TRUE

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

CREATE INDEX IF NOT EXISTS idx_meetups_creator
ON meetups(creator_id);

CREATE INDEX IF NOT EXISTS idx_meetups_starts_at
ON meetups(starts_at);

CREATE INDEX IF NOT EXISTS idx_meetups_active
ON meetups(active);

CREATE INDEX IF NOT EXISTS idx_meetup_participants_user
ON meetup_participants(user_id);
“””

class Storage(Protocol):
async def open(self) -> None: …

async def close(self) -> None: ...
async def track_user(
    self,
    user_id: int,
    username: str | None,
) -> None: ...
async def create_meetup(
    self,
    creator_id: int,
    title: str,
    place: str,
    starts_at: datetime,
    description: str,
    max_participants: int,
) -> int: ...
async def get_meetup(
    self,
    meetup_id: int,
): ...
async def get_active_meetups(self): ...
async def get_my_meetups(
    self,
    user_id: int,
): ...
async def join_meetup(
    self,
    meetup_id: int,
    user_id: int,
) -> tuple[bool, str]: ...
async def leave_meetup(
    self,
    meetup_id: int,
    user_id: int,
) -> bool: ...
async def get_participants(
    self,
    meetup_id: int,
): ...
async def is_participant(
    self,
    meetup_id: int,
    user_id: int,
) -> bool: ...
async def participant_count(
    self,
    meetup_id: int,
) -> int: ...
async def cleanup_finished_meetups(self) -> int: ...
async def user_count(self) -> int: ...
@property
def backend(self) -> str: ...

class MemoryStorage:
def init(self) -> None:
self._users: dict[int, str | None] = {}

    self._meetups: dict[int, dict] = {}
    self._participants: dict[
        int,
        set[int],
    ] = {}
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
async def create_meetup(
    self,
    creator_id: int,
    title: str,
    place: str,
    starts_at: datetime,
    description: str,
    max_participants: int,
) -> int:
    meetup_id = self._next_meetup_id
    self._next_meetup_id += 1
    self._meetups[meetup_id] = {
        "meetup_id": meetup_id,
        "creator_id": creator_id,
        "title": title,
        "place": place,
        "starts_at": starts_at,
        "description": description,
        "max_participants": max_participants,
        "created_at": datetime.now(timezone.utc),
        "active": True,
    }
    self._participants[meetup_id] = {
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
    if not meetup["active"]:
        return None
    data = dict(meetup)
    data["participant_count"] = len(
        self._participants.get(
            meetup_id,
            set(),
        )
    )
    return data
async def get_active_meetups(self):
    result = []
    now = datetime.now(timezone.utc)
    for meetup_id, meetup in self._meetups.items():
        if not meetup["active"]:
            continue
        if meetup["starts_at"] + timedelta(
            hours=24
        ) <= now:
            continue
        data = dict(meetup)
        data["participant_count"] = len(
            self._participants.get(
                meetup_id,
                set(),
            )
        )
        result.append(data)
    result.sort(
        key=lambda item: item["starts_at"]
    )
    return result
async def get_my_meetups(
    self,
    user_id: int,
):
    result = []
    for meetup_id, meetup in self._meetups.items():
        if not meetup["active"]:
            continue
        participants = self._participants.get(
            meetup_id,
            set(),
        )
        if (
            meetup["creator_id"] == user_id
            or user_id in participants
        ):
            data = dict(meetup)
            data["participant_count"] = len(
                participants
            )
            result.append(data)
    result.sort(
        key=lambda item: item["starts_at"]
    )
    return result
async def join_meetup(
    self,
    meetup_id: int,
    user_id: int,
) -> tuple[bool, str]:
    meetup = self._meetups.get(meetup_id)
    if not meetup or not meetup["active"]:
        return False, "not_found"
    now = datetime.now(timezone.utc)
    if meetup["starts_at"] + timedelta(
        hours=24
    ) <= now:
        return False, "expired"
    participants = self._participants.setdefault(
        meetup_id,
        set(),
    )
    if user_id in participants:
        return False, "already_joined"
    if len(participants) >= meetup["max_participants"]:
        return False, "full"
    participants.add(user_id)
    return True, "joined"
async def leave_meetup(
    self,
    meetup_id: int,
    user_id: int,
) -> bool:
    meetup = self._meetups.get(meetup_id)
    if not meetup:
        return False
    # Создатель не может выйти.
    if meetup["creator_id"] == user_id:
        return False
    participants = self._participants.get(
        meetup_id,
        set(),
    )
    if user_id not in participants:
        return False
    participants.remove(user_id)
    return True
async def get_participants(
    self,
    meetup_id: int,
):
    participants = self._participants.get(
        meetup_id,
        set(),
    )
    result = []
    for user_id in participants:
        result.append(
            {
                "user_id": user_id,
                "username": self._users.get(user_id),
                "is_creator": (
                    self._meetups[meetup_id][
                        "creator_id"
                    ]
                    == user_id
                ),
            }
        )
    return result
async def is_participant(
    self,
    meetup_id: int,
    user_id: int,
) -> bool:
    meetup = self._meetups.get(meetup_id)
    if not meetup:
        return False
    return (
        meetup["creator_id"] == user_id
        or user_id
        in self._participants.get(
            meetup_id,
            set(),
        )
    )
async def participant_count(
    self,
    meetup_id: int,
) -> int:
    return len(
        self._participants.get(
            meetup_id,
            set(),
        )
    )
async def cleanup_finished_meetups(
    self,
) -> int:
    now = datetime.now(timezone.utc)
    cleaned = 0
    for meetup_id, meetup in list(
        self._meetups.items()
    ):
        if not meetup["active"]:
            continue
        expires_at = (
            meetup["starts_at"]
            + timedelta(hours=24)
        )
        if expires_at <= now:
            creator_id = meetup[
                "creator_id"
            ]
            self._participants[meetup_id] = {
                creator_id
            }
            meetup["active"] = False
            cleaned += 1
    return cleaned
async def user_count(self) -> int:
    return len(self._users)

class PostgresStorage:
def init(
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
async def create_meetup(
    self,
    creator_id: int,
    title: str,
    place: str,
    starts_at: datetime,
    description: str,
    max_participants: int,
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
                    place,
                    starts_at,
                    description,
                    max_participants
                )
                VALUES
                ($1,$2,$3,$4,$5,$6)
                RETURNING meetup_id
                """,
                creator_id,
                title,
                place,
                starts_at,
                description,
                max_participants,
            )
            await conn.execute(
                """
                INSERT INTO meetup_participants
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
            COUNT(mp.user_id)::int
                AS participant_count
        FROM meetups m
        LEFT JOIN meetup_participants mp
            ON mp.meetup_id = m.meetup_id
        WHERE m.meetup_id = $1
          AND m.active = TRUE
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
            COUNT(mp.user_id)::int
                AS participant_count
        FROM meetups m
        LEFT JOIN meetup_participants mp
            ON mp.meetup_id = m.meetup_id
        WHERE m.active = TRUE
          AND m.starts_at
              + INTERVAL '24 hours'
              > now()
        GROUP BY m.meetup_id
        ORDER BY m.starts_at ASC
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
            COUNT(mp2.user_id)::int
                AS participant_count
        FROM meetups m
        LEFT JOIN meetup_participants mp2
            ON mp2.meetup_id = m.meetup_id
        WHERE m.active = TRUE
          AND (
              m.creator_id = $1
              OR EXISTS (
                  SELECT 1
                  FROM meetup_participants mp
                  WHERE mp.meetup_id = m.meetup_id
                    AND mp.user_id = $1
              )
          )
        GROUP BY m.meetup_id
        ORDER BY m.starts_at ASC
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
                SELECT
                    *
                FROM meetups
                WHERE meetup_id = $1
                  AND active = TRUE
                FOR UPDATE
                """,
                meetup_id,
            )
            if not meetup:
                return False, "not_found"
            expires_at = (
                meetup["starts_at"]
                + timedelta(hours=24)
            )
            if expires_at <= datetime.now(
                timezone.utc
            ):
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
            if count >= meetup[
                "max_participants"
            ]:
                return False, "full"
            await conn.execute(
                """
                INSERT INTO meetup_participants
                (
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
    creator_id = await self._pool.fetchval(
        """
        SELECT creator_id
        FROM meetups
        WHERE meetup_id = $1
        """,
        meetup_id,
    )
    if creator_id is None:
        return False
    # Создатель всегда остаётся.
    if creator_id == user_id:
        return False
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
            CASE
                WHEN m.creator_id = u.user_id
                THEN TRUE
                ELSE FALSE
            END AS is_creator
        FROM meetup_participants mp
        JOIN bot_users u
            ON u.user_id = mp.user_id
        JOIN meetups m
            ON m.meetup_id = mp.meetup_id
        WHERE mp.meetup_id = $1
        ORDER BY
            is_creator DESC,
            mp.joined_at ASC
        """,
        meetup_id,
    )
async def is_participant(
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
                FROM meetup_participants
                WHERE meetup_id = $1
                  AND user_id = $2
            )
            """,
            meetup_id,
            user_id,
        )
    )
async def participant_count(
    self,
    meetup_id: int,
) -> int:
    assert self._pool is not None
    count = await self._pool.fetchval(
        """
        SELECT COUNT(*)
        FROM meetup_participants
        WHERE meetup_id = $1
        """,
        meetup_id,
    )
    return int(count or 0)
async def cleanup_finished_meetups(
    self,
) -> int:
    assert self._pool is not None
    async with self._pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """
                SELECT meetup_id
                FROM meetups
                WHERE active = TRUE
                  AND starts_at
                      + INTERVAL '24 hours'
                      <= now()
                """
            )
            if not rows:
                return 0
            meetup_ids = [
                row["meetup_id"]
                for row in rows
            ]
            # Удаляем всех участников,
            # кроме создателя.
            await conn.execute(
                """
                DELETE FROM meetup_participants mp
                USING meetups m
                WHERE mp.meetup_id = m.meetup_id
                  AND m.meetup_id = ANY($1::bigint[])
                  AND mp.user_id != m.creator_id
                """,
                meetup_ids,
            )
            await conn.execute(
                """
                UPDATE meetups
                SET active = FALSE
                WHERE meetup_id = ANY(
                    $1::bigint[]
                )
                """,
                meetup_ids,
            )
    return len(rows)
async def user_count(self) -> int:
    assert self._pool is not None
    count = await self._pool.fetchval(
        """
        SELECT COUNT(*)
        FROM bot_users
        """
    )
    return int(count or 0)

def create_storage(
database_url: str | None,
) -> Storage:

if database_url:
    return PostgresStorage(
        database_url
    )
return MemoryStorage()
