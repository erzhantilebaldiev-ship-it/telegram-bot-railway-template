from future import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Protocol

import asyncpg

logger = logging.getLogger(name)

============================================================

DATABASE SCHEMA

============================================================

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
ends_at TIMESTAMPTZ NOT NULL,
cleanup_at TIMESTAMPTZ NOT NULL,
description TEXT NOT NULL DEFAULT '',
max_participants INTEGER NOT NULL
    CHECK (
        max_participants >= 1
        AND max_participants <= 100
    ),
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

CREATE INDEX IF NOT EXISTS idx_meetups_creator
ON meetups(creator_id);

CREATE INDEX IF NOT EXISTS idx_meetups_starts_at
ON meetups(starts_at);

CREATE INDEX IF NOT EXISTS idx_meetups_ends_at
ON meetups(ends_at);

CREATE INDEX IF NOT EXISTS idx_meetups_cleanup_at
ON meetups(cleanup_at);

CREATE INDEX IF NOT EXISTS idx_meetups_active
ON meetups(active);

CREATE INDEX IF NOT EXISTS idx_meetups_telegram_chat
ON meetups(telegram_chat_id);

CREATE INDEX IF NOT EXISTS idx_meetup_participants_user
ON meetup_participants(user_id);
“””

============================================================

STORAGE INTERFACE

============================================================

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
    telegram_chat_id: int | None = None,
) -> int:
    ...
async def get_meetup(
    self,
    meetup_id: int,
):
    ...
async def get_active_meetups(self):
    ...
async def get_my_meetups(
    self,
    user_id: int,
):
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
async def get_participants(
    self,
    meetup_id: int,
):
    ...
async def is_participant(
    self,
    meetup_id: int,
    user_id: int,
) -> bool:
    ...
async def participant_count(
    self,
    meetup_id: int,
) -> int:
    ...
async def set_telegram_chat_id(
    self,
    meetup_id: int,
    chat_id: int,
) -> bool:
    ...
async def get_meetup_by_chat_id(
    self,
    chat_id: int,
):
    ...
async def get_meetups_ready_for_cleanup(self):
    ...
async def mark_meetup_cleaned(
    self,
    meetup_id: int,
) -> bool:
    ...
async def cleanup_finished_meetups(self) -> int:
    ...
async def user_count(self) -> int:
    ...

============================================================

MEMORY STORAGE

============================================================

class MemoryStorage:

def __init__(self) -> None:
    self._users: dict[
        int,
        str | None,
    ] = {}
    self._meetups: dict[
        int,
        dict,
    ] = {}
    self._participants: dict[
        int,
        set[int],
    ] = {}
    self._next_meetup_id = 1
@property
def backend(self) -> str:
    return "memory"
async def open(self) -> None:
    logger.info(
        "storage.open backend=memory"
    )
async def close(self) -> None:
    return None
# --------------------------------------------------------
# USERS
# --------------------------------------------------------
async def track_user(
    self,
    user_id: int,
    username: str | None,
) -> None:
    self._users[user_id] = username
# --------------------------------------------------------
# CREATE MEETUP
# --------------------------------------------------------
async def create_meetup(
    self,
    creator_id: int,
    title: str,
    place: str,
    starts_at: datetime,
    ends_at: datetime,
    description: str,
    max_participants: int,
    telegram_chat_id: int | None = None,
) -> int:
    if ends_at <= starts_at:
        raise ValueError(
            "ends_at must be after starts_at"
        )
    cleanup_at = (
        ends_at + timedelta(hours=24)
    )
    meetup_id = self._next_meetup_id
    self._next_meetup_id += 1
    self._meetups[meetup_id] = {
        "meetup_id": meetup_id,
        "creator_id": creator_id,
        "title": title,
        "place": place,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "cleanup_at": cleanup_at,
        "description": description,
        "max_participants": max_participants,
        "telegram_chat_id": telegram_chat_id,
        "created_at": datetime.now(
            timezone.utc
        ),
        "active": True,
        "cleaned": False,
    }
    self._participants[meetup_id] = set()
    return meetup_id
# --------------------------------------------------------
# GET MEETUP
# --------------------------------------------------------
async def get_meetup(
    self,
    meetup_id: int,
):
    meetup = self._meetups.get(
        meetup_id
    )
    if not meetup:
        return None
    if meetup["cleaned"]:
        return None
    data = dict(meetup)
    data["participant_count"] = len(
        self._participants.get(
            meetup_id,
            set(),
        )
    )
    return data
# --------------------------------------------------------
# ACTIVE MEETUPS
# --------------------------------------------------------
async def get_active_meetups(self):
    now = datetime.now(
        timezone.utc
    )
    result = []
    for meetup in self._meetups.values():
        if not meetup["active"]:
            continue
        if meetup["cleaned"]:
            continue
        if meetup["cleanup_at"] <= now:
            continue
        data = dict(meetup)
        data["participant_count"] = len(
            self._participants.get(
                meetup["meetup_id"],
                set(),
            )
        )
        result.append(data)
    result.sort(
        key=lambda item: item["starts_at"]
    )
    return result
# --------------------------------------------------------
# MY MEETUPS
# --------------------------------------------------------
async def get_my_meetups(
    self,
    user_id: int,
):
    result = []
    for meetup_id, meetup in self._meetups.items():
        if meetup["cleaned"]:
            continue
        participants = self._participants.get(
            meetup_id,
            set(),
        )
        if user_id in participants:
            data = dict(meetup)
            data["participant_count"] = len(
                participants
            )
            result.append(data)
    result.sort(
        key=lambda item: item["starts_at"]
    )
    return result
# --------------------------------------------------------
# JOIN
# --------------------------------------------------------
async def join_meetup(
    self,
    meetup_id: int,
    user_id: int,
) -> tuple[bool, str]:
    meetup = self._meetups.get(
        meetup_id
    )
    if not meetup:
        return False, "not_found"
    if meetup["cleaned"]:
        return False, "closed"
    if not meetup["active"]:
        return False, "closed"
    now = datetime.now(
        timezone.utc
    )
    # После окончания + 24 часа
    # новые участники уже невозможны.
    if meetup["cleanup_at"] <= now:
        return False, "expired"
    participants = self._participants.setdefault(
        meetup_id,
        set(),
    )
    if user_id in participants:
        return False, "already_joined"
    if len(participants) >= meetup[
        "max_participants"
    ]:
        return False, "full"
    participants.add(user_id)
    return True, "joined"
# --------------------------------------------------------
# LEAVE
# --------------------------------------------------------
async def leave_meetup(
    self,
    meetup_id: int,
    user_id: int,
) -> bool:
    participants = self._participants.get(
        meetup_id
    )
    if not participants:
        return False
    if user_id not in participants:
        return False
    participants.remove(user_id)
    return True
# --------------------------------------------------------
# PARTICIPANTS
# --------------------------------------------------------
async def get_participants(
    self,
    meetup_id: int,
):
    meetup = self._meetups.get(
        meetup_id
    )
    if not meetup:
        return []
    participants = self._participants.get(
        meetup_id,
        set(),
    )
    result = []
    for user_id in participants:
        result.append(
            {
                "user_id": user_id,
                "username": self._users.get(
                    user_id
                ),
            }
        )
    return result
async def is_participant(
    self,
    meetup_id: int,
    user_id: int,
) -> bool:
    return user_id in self._participants.get(
        meetup_id,
        set(),
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
# --------------------------------------------------------
# TELEGRAM GROUP
# --------------------------------------------------------
async def set_telegram_chat_id(
    self,
    meetup_id: int,
    chat_id: int,
) -> bool:
    meetup = self._meetups.get(
        meetup_id
    )
    if not meetup:
        return False
    meetup["telegram_chat_id"] = chat_id
    return True
async def get_meetup_by_chat_id(
    self,
    chat_id: int,
):
    for meetup in self._meetups.values():
        if meetup[
            "telegram_chat_id"
        ] == chat_id:
            return dict(meetup)
    return None
# --------------------------------------------------------
# READY FOR CLEANUP
# --------------------------------------------------------
async def get_meetups_ready_for_cleanup(
    self,
):
    now = datetime.now(
        timezone.utc
    )
    result = []
    for meetup in self._meetups.values():
        if meetup["cleaned"]:
            continue
        if meetup["cleanup_at"] <= now:
            result.append(
                dict(meetup)
            )
    return result
# --------------------------------------------------------
# MARK CLEANED
# --------------------------------------------------------
async def mark_meetup_cleaned(
    self,
    meetup_id: int,
) -> bool:
    meetup = self._meetups.get(
        meetup_id
    )
    if not meetup:
        return False
    meetup["active"] = False
    meetup["cleaned"] = True
    # В базе участники тоже удаляются.
    self._participants[
        meetup_id
    ] = set()
    return True
# --------------------------------------------------------
# CLEANUP
# --------------------------------------------------------
async def cleanup_finished_meetups(
    self,
) -> int:
    meetups = (
        await self.get_meetups_ready_for_cleanup()
    )
    cleaned = 0
    for meetup in meetups:
        meetup_id = meetup[
            "meetup_id"
        ]
        await self.mark_meetup_cleaned(
            meetup_id
        )
        cleaned += 1
    return cleaned
async def user_count(self) -> int:
    return len(self._users)

============================================================

POSTGRES STORAGE

============================================================

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
# --------------------------------------------------------
# OPEN
# --------------------------------------------------------
async def open(self) -> None:
    self._pool = await asyncpg.create_pool(
        self._dsn,
        min_size=1,
        max_size=5,
    )
    async with self._pool.acquire() as conn:
        await conn.execute(
            _SCHEMA
        )
        # Миграция для существующей базы.
        await conn.execute(
            """
            ALTER TABLE meetups
            ADD COLUMN IF NOT EXISTS ends_at
            TIMESTAMPTZ
            """
        )
        await conn.execute(
            """
            ALTER TABLE meetups
            ADD COLUMN IF NOT EXISTS cleanup_at
            TIMESTAMPTZ
            """
        )
        await conn.execute(
            """
            ALTER TABLE meetups
            ADD COLUMN IF NOT EXISTS telegram_chat_id
            BIGINT
            """
        )
        await conn.execute(
            """
            ALTER TABLE meetups
            ADD COLUMN IF NOT EXISTS cleaned
            BOOLEAN NOT NULL DEFAULT FALSE
            """
        )
    logger.info(
        "storage.open backend=postgres"
    )
# --------------------------------------------------------
# CLOSE
# --------------------------------------------------------
async def close(self) -> None:
    if self._pool is not None:
        await self._pool.close()
        self._pool = None
# --------------------------------------------------------
# USERS
# --------------------------------------------------------
async def track_user(
    self,
    user_id: int,
    username: str | None,
) -> None:
    assert self._pool is not None
    await self._pool.execute(
        """
        INSERT INTO bot_users
        (
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
# --------------------------------------------------------
# CREATE MEETUP
# --------------------------------------------------------
async def create_meetup(
    self,
    creator_id: int,
    title: str,
    place: str,
    starts_at: datetime,
    ends_at: datetime,
    description: str,
    max_participants: int,
    telegram_chat_id: int | None = None,
) -> int:
    assert self._pool is not None
    if ends_at <= starts_at:
        raise ValueError(
            "ends_at must be after starts_at"
        )
    cleanup_at = (
        ends_at + timedelta(hours=24)
    )
    async with self._pool.acquire() as conn:
        meetup_id = await conn.fetchval(
            """
            INSERT INTO meetups
            (
                creator_id,
                title,
                place,
                starts_at,
                ends_at,
                cleanup_at,
                description,
                max_participants,
                telegram_chat_id
            )
            VALUES
            (
                $1,
                $2,
                $3,
                $4,
                $5,
                $6,
                $7,
                $8,
                $9
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
            telegram_chat_id,
        )
    return int(meetup_id)
# --------------------------------------------------------
# GET MEETUP
# --------------------------------------------------------
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
          AND m.cleaned = FALSE
        GROUP BY m.meetup_id
        """,
        meetup_id,
    )
# --------------------------------------------------------
# ACTIVE MEETUPS
# --------------------------------------------------------
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
          AND m.cleaned = FALSE
          AND m.cleanup_at > now()
        GROUP BY m.meetup_id
        ORDER BY m.starts_at ASC
        """
    )
# --------------------------------------------------------
# MY MEETUPS
# --------------------------------------------------------
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
          AND m.cleaned = FALSE
          AND EXISTS (
              SELECT 1
              FROM meetup_participants mp
              WHERE mp.meetup_id = m.meetup_id
                AND mp.user_id = $1
          )
        GROUP BY m.meetup_id
        ORDER BY m.starts_at ASC
        """,
        user_id,
    )
# --------------------------------------------------------
# JOIN
# --------------------------------------------------------
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
            now = datetime.now(
                timezone.utc
            )
            # После окончания + 24 часа
            # вступление запрещено.
            if meetup[
                "cleanup_at"
            ] <= now:
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
                VALUES ($1, $2)
                """,
                meetup_id,
                user_id,
            )
    return True, "joined"
# --------------------------------------------------------
# LEAVE
# --------------------------------------------------------
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
# --------------------------------------------------------
# PARTICIPANTS
# --------------------------------------------------------
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
        ORDER BY mp.joined_at ASC
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
# --------------------------------------------------------
# TELEGRAM CHAT
# --------------------------------------------------------
async def set_telegram_chat_id(
    self,
    meetup_id: int,
    chat_id: int,
) -> bool:
    assert self._pool is not None
    result = await self._pool.execute(
        """
        UPDATE meetups
        SET telegram_chat_id = $2
        WHERE meetup_id = $1
        """,
        meetup_id,
        chat_id,
    )
    return result.endswith("1")
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
        """,
        chat_id,
    )
# --------------------------------------------------------
# MEETUPS READY FOR CLEANUP
# --------------------------------------------------------
async def get_meetups_ready_for_cleanup(
    self,
):
    assert self._pool is not None
    return await self._pool.fetch(
        """
        SELECT *
        FROM meetups
        WHERE cleaned = FALSE
          AND cleanup_at <= now()
        ORDER BY cleanup_at ASC
        """
    )
# --------------------------------------------------------
# MARK CLEANED
# --------------------------------------------------------
async def mark_meetup_cleaned(
    self,
    meetup_id: int,
) -> bool:
    assert self._pool is not None
    async with self._pool.acquire() as conn:
        async with conn.transaction():
            # Сначала удаляем ВСЕХ участников.
            await conn.execute(
                """
                DELETE FROM meetup_participants
                WHERE meetup_id = $1
                """,
                meetup_id,
            )
            # Затем закрываем сходку.
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
# --------------------------------------------------------
# CLEANUP
# --------------------------------------------------------
async def cleanup_finished_meetups(
    self,
) -> int:
    meetups = (
        await self
        .get_meetups_ready_for_cleanup()
    )
    cleaned = 0
    for meetup in meetups:
        meetup_id = meetup[
            "meetup_id"
        ]
        success = (
            await self
            .mark_meetup_cleaned(
                meetup_id
            )
        )
        if success:
            cleaned += 1
    return cleaned
# --------------------------------------------------------
# USER COUNT
# --------------------------------------------------------
async def user_count(self) -> int:
    assert self._pool is not None
    count = await self._pool.fetchval(
        """
        SELECT COUNT(*)
        FROM bot_users
        """
    )
    return int(count or 0)

============================================================

STORAGE FACTORY

============================================================

def create_storage(
database_url: str | None,
) -> Storage:

if database_url:
    return PostgresStorage(
        database_url
    )
logger.warning(
    "DATABASE_URL is not configured; "
    "using temporary memory storage"
)
return MemoryStorage()
