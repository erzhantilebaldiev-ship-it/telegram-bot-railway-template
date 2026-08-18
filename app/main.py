from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import (
    SimpleRequestHandler,
    setup_application,
)
from aiohttp import web

from config import Config, load_config
from db import Storage, create_storage
from handlers import router


logger = logging.getLogger("bot")


# ============================================================
# JSON LOGGING
# ============================================================

class JsonFormatter(logging.Formatter):
    """JSON-формат логов для Railway."""

    def format(
        self,
        record: logging.LogRecord,
    ) -> str:

        entry: dict[str, object] = {
            "ts": datetime.now(
                timezone.utc
            ).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            entry["exc"] = self.formatException(
                record.exc_info
            )

        return json.dumps(
            entry,
            ensure_ascii=False,
        )


def setup_logging(
    level: str,
) -> None:

    handler = logging.StreamHandler(
        sys.stdout
    )

    handler.setFormatter(
        JsonFormatter()
    )

    logging.basicConfig(
        level=level,
        handlers=[handler],
    )


# ============================================================
# HEALTHCHECK
# ============================================================

async def healthz(
    request: web.Request,
) -> web.Response:

    db: Storage = request.app["db"]

    return web.json_response(
        {
            "status": "ok",
            "storage": db.backend,
        }
    )


# ============================================================
# УДАЛЕНИЕ УЧАСТНИКОВ ИЗ TELEGRAM
# ============================================================

async def remove_user_from_group(
    bot: Bot,
    chat_id: int,
    user_id: int,
) -> bool:
    """
    Удаляет пользователя из Telegram-группы.

    Используем:
    ban_chat_member()
    затем
    unban_chat_member()

    Благодаря этому пользователь удаляется,
    но после этого может снова вступить по новой
    пригласительной ссылке.

    Важно:
    бот должен быть администратором группы
    с правом блокировать пользователей.
    """

    try:
        await bot.ban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
        )

        await bot.unban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            only_if_banned=True,
        )

        logger.info(
            "user removed from meetup group "
            "chat_id=%s user_id=%s",
            chat_id,
            user_id,
        )

        return True

    except Exception:
        logger.exception(
            "failed to remove user from group "
            "chat_id=%s user_id=%s",
            chat_id,
            user_id,
        )

        return False


# ============================================================
# ОЧИСТКА ЗАВЕРШЁННЫХ СХОДОК
# ============================================================

async def cleanup_meetup(
    bot: Bot,
    storage: Storage,
    meetup,
) -> None:
    """
    Полная очистка одной сходки.

    1. Получаем Telegram-группу.
    2. Получаем участников из БД.
    3. Удаляем участников из Telegram-группы.
    4. Помечаем сходку очищенной в PostgreSQL.
    5. Сама группа остаётся существовать.
    """

    meetup_id = meetup["meetup_id"]

    chat_id = meetup.get(
        "telegram_chat_id"
    )

    logger.info(
        "starting meetup cleanup "
        "meetup_id=%s chat_id=%s",
        meetup_id,
        chat_id,
    )

    # Если Telegram-группа привязана.
    if chat_id:

        participants = await storage.get_participants(
            meetup_id
        )

        logger.info(
            "removing %d participants "
            "from meetup_id=%s",
            len(participants),
            meetup_id,
        )

        for participant in participants:

            user_id = participant["user_id"]

            await remove_user_from_group(
                bot=bot,
                chat_id=chat_id,
                user_id=user_id,
            )

            # Небольшая пауза,
            # чтобы не создавать лишнюю нагрузку
            # на Telegram API.
            await asyncio.sleep(0.05)

    # После удаления людей из Telegram
    # очищаем данные сходки в PostgreSQL.
    cleaned = await storage.mark_meetup_cleaned(
        meetup_id
    )

    if cleaned:
        logger.info(
            "meetup cleanup completed "
            "meetup_id=%s",
            meetup_id,
        )


async def meetup_cleanup_loop(
    bot: Bot,
    storage: Storage,
) -> None:
    """
    Фоновая проверка завершённых сходок.

    Каждые 60 секунд:

    - ищем сходки, у которых прошло 24 часа
      после окончания;
    - удаляем участников из Telegram-группы;
    - очищаем участников из PostgreSQL;
    - освобождаем постоянную группу.

    Сама Telegram-группа НЕ удаляется.
    """

    logger.info(
        "meetup cleanup loop started"
    )

    while True:

        try:

            meetups = (
                await storage
                .get_meetups_ready_for_cleanup()
            )

            if meetups:

                logger.info(
                    "found %d meetups ready "
                    "for cleanup",
                    len(meetups),
                )

            for meetup in meetups:

                try:

                    await cleanup_meetup(
                        bot=bot,
                        storage=storage,
                        meetup=meetup,
                    )

                except Exception:
                    logger.exception(
                        "cleanup failed "
                        "meetup_id=%s",
                        meetup["meetup_id"],
                    )

        except asyncio.CancelledError:

            logger.info(
                "meetup cleanup loop stopped"
            )

            raise

        except Exception:

            logger.exception(
                "meetup cleanup loop failed"
            )

        await asyncio.sleep(60)


# ============================================================
# BUILD APP
# ============================================================

def build_app(
    config: Config,
) -> web.Application:
    """
    Создание aiohttp-приложения,
    Telegram-бота и PostgreSQL storage.
    """

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )

    dispatcher = Dispatcher()

    dispatcher.include_router(
        router
    )

    storage = create_storage(
        config.database_url
    )

    # Доступ к БД из handlers.py:
    #
    # async def handler(
    #     message: Message,
    #     db: Storage,
    # )
    #
    dispatcher["db"] = storage

    cleanup_task: asyncio.Task | None = None

    # ========================================================
    # STARTUP
    # ========================================================

    async def on_startup(
        bot: Bot,
    ) -> None:

        nonlocal cleanup_task

        logger.info(
            "opening storage"
        )

        await storage.open()

        logger.info(
            "storage opened backend=%s",
            storage.backend,
        )

        # ----------------------------------------------------
        # Фоновая очистка сходок
        # ----------------------------------------------------

        cleanup_task = asyncio.create_task(
            meetup_cleanup_loop(
                bot=bot,
                storage=storage,
            )
        )

        logger.info(
            "meetup cleanup task started"
        )

        # ----------------------------------------------------
        # Telegram webhook
        # ----------------------------------------------------

        await bot.set_webhook(
            url=config.webhook_url,
            secret_token=config.webhook_secret,
            drop_pending_updates=(
                config.drop_pending_updates
            ),
            allowed_updates=[
                "message",
                "callback_query",
            ],
        )

        me = await bot.get_me()

        logger.info(
            "webhook registered "
            "bot=@%s url=%s storage=%s",
            me.username,
            config.webhook_url,
            storage.backend,
        )


    # ========================================================
    # SHUTDOWN
    # ========================================================

    async def on_shutdown(
        bot: Bot,
    ) -> None:

        nonlocal cleanup_task

        # ----------------------------------------------------
        # Останавливаем очистку
        # ----------------------------------------------------

        if cleanup_task is not None:

            logger.info(
                "stopping meetup cleanup task"
            )

            cleanup_task.cancel()

            try:
                await cleanup_task

            except asyncio.CancelledError:
                pass

            cleanup_task = None

        # ----------------------------------------------------
        # Закрываем PostgreSQL
        # ----------------------------------------------------

        await storage.close()

        # ----------------------------------------------------
        # Закрываем Telegram session
        # ----------------------------------------------------

        await bot.session.close()

        logger.info(
            "shutdown complete"
        )


    dispatcher.startup.register(
        on_startup
    )

    dispatcher.shutdown.register(
        on_shutdown
    )

    # ========================================================
    # AIOHTTP APP
    # ========================================================

    app = web.Application()

    app["db"] = storage

    # --------------------------------------------------------
    # Railway healthcheck
    # --------------------------------------------------------

    app.router.add_get(
        "/healthz",
        healthz,
    )

    # --------------------------------------------------------
    # Telegram webhook
    # --------------------------------------------------------

    SimpleRequestHandler(
        dispatcher=dispatcher,
        bot=bot,
        secret_token=config.webhook_secret,
    ).register(
        app,
        path=config.webhook_path,
    )

    # --------------------------------------------------------
    # Lifecycle aiogram + aiohttp
    # --------------------------------------------------------

    setup_application(
        app,
        dispatcher,
        bot=bot,
    )

    return app


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    config = load_config()

    setup_logging(
        config.log_level
    )

    logger.info(
        "starting server "
        "port=%d domain=%s",
        config.port,
        config.public_domain,
    )

    web.run_app(
        build_app(config),
        host="0.0.0.0",
        port=config.port,
        print=None,
    )


if __name__ == "__main__":
    main()
