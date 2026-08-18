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

CREATE TABLE IF NOT EXISTS swipes (
    user_id BIGINT NOT NULL REFERENCES bot_users(user_id) ON DELETE CASCADE,
    target_id BIGINT NOT NULL REFERENCES bot_users(user_id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, target_id)
);

CREATE TABLE IF NOT EXISTS blocked_users (
    user_id BIGINT NOT NULL REFERENCES bot_users(user_id) ON DELETE CASCADE,
    blocked_id BIGINT NOT NULL REFERENCES bot_users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, blocked_id)
);

CREATE INDEX IF NOT EXISTS idx_swipes_user
ON swipes(user_id);

CREATE INDEX IF NOT EXISTS idx_swipes_target
ON swipes(target_id);
"""


class Storage(Protocol):
    async def open(self) -> None: ...
    async def close(self) -> None: ...

    async def track_user(
        self,
        user_id: int,
        username: str | None,
    ) -> None: ...

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

    async def get_next_profile(self, user_id: int): ...

    async def swipe(
        self,
        user_id: int,
        target_id: int,
        action: str,
    ) -> bool: ...

    async def get_username(
        self,
        user_id: int,
    ) -> str | None: ...

    async def get_likes(
        self,
        user_id: int,
    ): ...

    async def delete_profile(
        self,
        user_id: int,
    ) -> None: ...

    async def block_user(
        self,
        user_id: int,
        blocked_id: int,
    ) -> None: ...

    async def user_count(self) -> int: ...

    @property
    def backend(self) -> str: ...


class MemoryStorage:
    def __init__(self) -> None:
        self._users: dict[int, str | None] = {}
        self._profiles: dict[int, dict] = {}
        self._swipes: dict[tuple[int, int], str] = {}
        self._blocked: set[tuple[int, int]] = set()

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
            "user_id": user_id,
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

    async def get_next_profile(self, user_id: int):
        me = self._profiles.get(user_id)

        if not me:
            return None

        for target_id, profile in self._profiles.items():
            if target_id == user_id:
                continue

            if (user_id, target_id) in self._blocked:
                continue

            if (target_id, user_id) in self._blocked:
                continue

            if (user_id, target_id) in self._swipes:
                continue

            if (
                profile["looking_for"] != "Неважно"
                and profile["looking_for"] != me["gender"]
                and not (
                    profile["looking_for"] == "Парней"
                    and me["gender"] == "Парень"
                )
                and not (
                    profile["looking_for"] == "Девушек"
                    and me["gender"] == "Девушка"
                )
            ):
                continue

            return profile

        return None

    async def swipe(
        self,
        user_id: int,
        target_id: int,
        action: str,
    ) -> bool:
        self._swipes[(user_id, target_id)] = action

        if action != "like":
            return False

        return (
            self._swipes.get((target_id, user_id))
            == "like"
        )

    async def get_username(
        self,
        user_id: int,
    ) -> str | None:
        return self._users.get(user_id)

    async def get_likes(self, user_id: int):
        result = []

        for (sender, target), action in self._swipes.items():
            if target == user_id and action == "like":
                profile = self._profiles.get(sender)

                if profile:
                    result.append(profile)

        return result

    async def delete_profile(
        self,
        user_id: int,
    ) -> None:
        self._profiles.pop(user_id, None)

        self._swipes = {
            key: value
            for key, value in self._swipes.items()
            if user_id not in key
        }

    async def block_user(
        self,
        user_id: int,
        blocked_id: int,
    ) -> None:
        self._blocked.add(
            (user_id, blocked_id)
        )

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
            (
                user_id,
                name,
                age,
                city,
                gender,
                looking_for,
                photo_file_id,
                bio
            )
            VALUES
            ($1,$2,$3,$4,$5,$6,$7,$8)
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

    async def get_profile(
        self,
        user_id: int,
    ):
        assert self._pool is not None

        return await self._pool.fetchrow(
            """
            SELECT *
            FROM profiles
            WHERE user_id = $1
            """,
            user_id,
        )

    async def get_next_profile(
        self,
        user_id: int,
    ):
        assert self._pool is not None

        return await self._pool.fetchrow(
            """
            SELECT p.*
            FROM profiles p
            JOIN profiles me
              ON me.user_id = $1
            WHERE p.user_id != $1

              AND NOT EXISTS (
                  SELECT 1
                  FROM swipes s
                  WHERE s.user_id = $1
                    AND s.target_id = p.user_id
              )

              AND NOT EXISTS (
                  SELECT 1
                  FROM blocked_users b
                  WHERE
                    (b.user_id = $1
                     AND b.blocked_id = p.user_id)
                    OR
                    (b.user_id = p.user_id
                     AND b.blocked_id = $1)
              )

              AND (
                  p.looking_for = 'Неважно'
                  OR
                  (
                      p.looking_for = 'Парней'
                      AND me.gender = 'Парень'
                  )
                  OR
                  (
                      p.looking_for = 'Девушек'
                      AND me.gender = 'Девушка'
                  )
              )

              AND (
                  me.looking_for = 'Неважно'
                  OR
                  (
                      me.looking_for = 'Парней'
                      AND p.gender = 'Парень'
                  )
                  OR
                  (
                      me.looking_for = 'Девушек'
                      AND p.gender = 'Девушка'
                  )
              )

            ORDER BY random()
            LIMIT 1
            """,
            user_id,
        )

    async def swipe(
        self,
        user_id: int,
        target_id: int,
        action: str,
    ) -> bool:
        assert self._pool is not None

        await self._pool.execute(
            """
            INSERT INTO swipes
            (user_id, target_id, action)
            VALUES ($1,$2,$3)
            ON CONFLICT (user_id,target_id)
            DO UPDATE SET action = EXCLUDED.action
            """,
            user_id,
            target_id,
            action,
        )

        if action != "like":
            return False

        return bool(
            await self._pool.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM swipes
                    WHERE user_id = $1
                      AND target_id = $2
                      AND action = 'like'
                )
                """,
                target_id,
                user_id,
            )
        )

    async def get_username(
        self,
        user_id: int,
    ) -> str | None:
        assert self._pool is not None

        return await self._pool.fetchval(
            """
            SELECT username
            FROM bot_users
            WHERE user_id = $1
            """,
            user_id,
        )

    async def get_likes(
        self,
        user_id: int,
    ):
        assert self._pool is not None

        return await self._pool.fetch(
            """
            SELECT p.*
            FROM swipes s
            JOIN profiles p
              ON p.user_id = s.user_id
            WHERE s.target_id = $1
              AND s.action = 'like'
            ORDER BY s.created_at DESC
            """,
            user_id,
        )

    async def delete_profile(
        self,
        user_id: int,
    ) -> None:
        assert self._pool is not None

        await self._pool.execute(
            """
            DELETE FROM profiles
            WHERE user_id = $1
            """,
            user_id,
        )

        await self._pool.execute(
            """
            DELETE FROM swipes
            WHERE user_id = $1
               OR target_id = $1
            """,
            user_id,
        )

    async def block_user(
        self,
        user_id: int,
        blocked_id: int,
    ) -> None:
        assert self._pool is not None

        await self._pool.execute(
            """
            INSERT INTO blocked_users
            (user_id, blocked_id)
            VALUES ($1,$2)
            ON CONFLICT DO NOTHING
            """,
            user_id,
            blocked_id,
        )

    async def user_count(self) -> int:
        assert self._pool is not None

        return await self._pool.fetchval(
            "SELECT count(*) FROM bot_users"
        )


def create_storage(
    database_url: str | None,
) -> Storage:
    if database_url:
        return PostgresStorage(database_url)

    return MemoryStorage()
