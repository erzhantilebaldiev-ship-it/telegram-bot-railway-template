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

CREATE TABLE IF NOT EXISTS profiles (
    user_id BIGINT PRIMARY KEY REFERENCES bot_users(user_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    age INTEGER NOT NULL,
    city TEXT NOT NULL,
    gender TEXT NOT NULL,
    looking_for TEXT NOT NULL,
    photo_file_id TEXT,
    bio TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


class Storage(Protocol):
    async def open(self) -> None: ...
    async def close(self) -> None: ...
    async def track_user(self, user_id: int, username: str | None) -> None: ...
    async def save_profile(
        self,
        user_id: int,
        name: str,
        age: int,
        city: str,
        gender: str,
        looking_for: str,
        photo_file_id: str | None,
        bio: str,
    ) -> None: ...
    async def get_profile(self, user_id: int): ...
    async def user_count(self) -> int: ...
    @property
    def backend(self) -> str: ...


class MemoryStorage:
    def __init__(self) -> None:
        self._users = {}
        self._profiles = {}

    @property
    def backend(self) -> str:
        return "memory"

    async def open(self) -> None:
        logger.info("storage.open backend=memory")

    async def close(self) -> None:
        return None

    async def track_user(self, user_id: int, username: str | None) -> None:
        self._users[user_id] = username

    async def save_profile(
        self,
        user_id: int,
        name: str,
        age: int,
        city: str,
        gender: str,
        looking_for: str,
        photo_file_id: str | None,
        bio: str,
    ) -> None:
        self._profiles[user_id] = {
            "name": name,
            "age": age,
            "city": city,
            "gender": gender,
            "looking_for": looking_for,
            "photo_file_id": photo_file_id,
            "bio": bio,
        }

    async def get_profile(self, user_id: int):
        return self._profiles.get(user_id)

    async def user_count(self) -> int:
        return len(self._users)


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

    async def track_user(self, user_id: int, username: str | None) -> None:
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

    async def save_profile(
        self,
        user_id: int,
        name: str,
        age: int,
        city: str,
        gender: str,
        looking_for: str,
        photo_file_id: str | None,
        bio: str,
    ) -> None:
        assert self._pool is not None

        await self._pool.execute(
            """
            INSERT INTO profiles
            (user_id, name, age, city, gender, looking_for, photo_file_id, bio)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (user_id)
            DO UPDATE SET
                name = EXCLUDED.name,
                age = EXCLUDED.age,
                city = EXCLUDED.city,
                gender = EXCLUDED.gender,
                looking_for = EXCLUDED.looking_for,
                photo_file_id = EXCLUDED.photo_file_id,
                bio = EXCLUDED.bio,
                updated_at = now()
            """,
            user_id,
            name,
            age,
            city,
            gender,
            looking_for,
            photo_file_id,
            bio,
        )

    async def get_profile(self, user_id: int):
        assert self._pool is not None

        return await self._pool.fetchrow(
            """
            SELECT name, age, city, gender,
                   looking_for, photo_file_id, bio
            FROM profiles
            WHERE user_id = $1
            """,
            user_id,
        )

    async def user_count(self) -> int:
        assert self._pool is not None
        return await self._pool.fetchval(
            "SELECT count(*) FROM bot_users"
        )


def create_storage(database_url: str | None) -> Storage:
    if database_url:
        return PostgresStorage(database_url)

    return MemoryStorage()
