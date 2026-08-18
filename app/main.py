“”“Entrypoint: aiohttp web server + aiogram webhook bot.

Webhook:
Telegram -> /telegram/webhook

Также работает фоновая задача:
каждые 60 секунд проверяет сходки
и закрывает те, которым исполнилось 24 часа.
“””

from future import annotations

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

logger = logging.getLogger(“bot”)

class JsonFormatter(logging.Formatter):
“”“One JSON object per line.”””

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

def setup_logging(level: str) -> None:

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

async def meetup_cleanup_loop(
storage: Storage,
) -> None:
“””
Проверяет завершённые сходки раз в минуту.

Если с момента начала сходки прошло 24 часа:
- все участники кроме создателя удаляются;
- сходка становится неактивной.
"""
while True:
    try:
        cleaned = (
            await storage
            .cleanup_finished_meetups()
        )
        if cleaned:
            logger.info(
                "meetup cleanup completed count=%d",
                cleaned,
            )
    except asyncio.CancelledError:
        logger.info(
            "meetup cleanup task stopped"
        )
        raise
    except Exception:
        logger.exception(
            "meetup cleanup failed"
        )
    await asyncio.sleep(60)

def build_app(
config: Config,
) -> web.Application:

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
# Передаём storage в handlers.py.
dispatcher["db"] = storage
# Ссылка на фоновую задачу.
cleanup_task: asyncio.Task | None = None
async def on_startup(
    bot: Bot,
) -> None:
    nonlocal cleanup_task
    # Открываем базу.
    await storage.open()
    # Запускаем автоматическую очистку.
    cleanup_task = asyncio.create_task(
        meetup_cleanup_loop(
            storage
        )
    )
    logger.info(
        "meetup cleanup task started"
    )
    # Регистрируем webhook.
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
        "webhook registered bot=@%s url=%s storage=%s",
        me.username,
        config.webhook_url,
        storage.backend,
    )
async def on_shutdown(
    bot: Bot,
) -> None:
    nonlocal cleanup_task
    # Останавливаем фоновую задачу.
    if cleanup_task is not None:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        cleanup_task = None
    logger.info(
        "meetup cleanup task stopped"
    )
    # Закрываем базу.
    await storage.close()
    # Закрываем Telegram-сессию.
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
app = web.Application()
app["db"] = storage
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
# Связываем lifecycle aiohttp
# с lifecycle aiogram.
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

if name == “main”:
main()
