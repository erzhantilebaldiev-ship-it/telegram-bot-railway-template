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


class JsonFormatter(logging.Formatter):
    """JSON-формат логов для Railway."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "ts": datetime.now(timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)

        return json.dumps(
            entry,
            ensure_ascii=False,
        )


def setup_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    logging.basicConfig(
        level=level,
        handlers=[handler],
    )


async def healthz(request: web.Request) -> web.Response:
    """Healthcheck для Railway."""

    db: Storage = request.app["db"]

    return web.json_response(
        {
            "status": "ok",
            "storage": db.backend,
        }
    )


async def meetup_cleanup_loop(
    storage: Storage,
) -> None:
    """
    Фоновая очистка завершённых сходок.

    Каждые 60 секунд проверяем PostgreSQL.

    Если прошло 24 часа после окончания сходки:
    - сходка закрывается;
    - участники удаляются из базы;
    - сама Telegram-группа НЕ удаляется.

    ВАЖНО:
    Фактическое удаление людей из Telegram-группы
    выполняется через Telegram Bot API в отдельной логике.
    """

    logger.info("meetup cleanup loop started")

    while True:
        try:
            cleaned = await storage.cleanup_finished_meetups()

            if cleaned:
                logger.info(
                    "meetup database cleanup completed count=%d",
                    cleaned,
                )

        except asyncio.CancelledError:
            logger.info("meetup cleanup loop stopped")
            raise

        except Exception:
            logger.exception("meetup cleanup failed")

        await asyncio.sleep(60)


def build_app(config: Config) -> web.Application:
    """Создание aiohttp-приложения и Telegram-бота."""

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )

    dispatcher = Dispatcher()

    dispatcher.include_router(router)

    storage = create_storage(
        config.database_url
    )

    # Доступ к базе из handlers.py:
    # async def handler(..., db: Storage)
    dispatcher["db"] = storage

    cleanup_task: asyncio.Task | None = None

    async def on_startup(bot: Bot) -> None:
        nonlocal cleanup_task

        logger.info("opening storage")

        await storage.open()

        logger.info(
            "storage opened backend=%s",
            storage.backend,
        )

        # Запускаем фоновую проверку сходок.
        cleanup_task = asyncio.create_task(
            meetup_cleanup_loop(storage)
        )

        logger.info(
            "meetup cleanup task started"
        )

        # Регистрируем webhook Telegram.
        await bot.set_webhook(
            url=config.webhook_url,
            secret_token=config.webhook_secret,
            drop_pending_updates=config.drop_pending_updates,
            allowed_updates=[
                "message",
                "callback_query",
            ],
        )

        me = await bot.get_me()

        logger.info(
            "webhook registered bot=@%s url=%s storage=%s",
            me.username,
            config.webhook_url,
            storage.backend,
        )

    async def on_shutdown(bot: Bot) -> None:
        nonlocal cleanup_task

        # Останавливаем фоновую задачу.
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

        # Закрываем базу.
        await storage.close()

        # Закрываем Telegram-сессию.
        await bot.session.close()

        logger.info("shutdown complete")

    dispatcher.startup.register(on_startup)
    dispatcher.shutdown.register(on_shutdown)

    app = web.Application()

    app["db"] = storage

    # Railway healthcheck.
    app.router.add_get(
        "/healthz",
        healthz,
    )

    # Telegram webhook.
    SimpleRequestHandler(
        dispatcher=dispatcher,
        bot=bot,
        secret_token=config.webhook_secret,
    ).register(
        app,
        path=config.webhook_path,
    )

    # Подключаем lifecycle aiogram к aiohttp.
    setup_application(
        app,
        dispatcher,
        bot=bot,
    )

    return app


def main() -> None:
    config = load_config()

    setup_logging(
        config.log_level
    )

    logger.info(
        "starting server port=%d domain=%s",
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
