from __future__ import annotations

import asyncio
import sys

from aiohttp import web
from loguru import logger
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app.config import settings
from app.db import init_db
from app.bot.handlers import BotHandlers
from app.scheduler.broadcast_scheduler import BroadcastScheduler
from app.web.miniapp import setup_miniapp_routes


async def main() -> None:
    logger.remove()
    logger.add('logs/app.log', rotation='20 MB', level=settings.log_level)
    logger.add(sys.stdout, level=settings.log_level)

    await init_db()

    handlers = BotHandlers()
    tg_app = Application.builder().token(settings.bot_token).updater(None).build()
    tg_app.add_handler(CommandHandler('start', handlers.start))
    tg_app.add_handler(CallbackQueryHandler(handlers.callback))
    tg_app.add_handler(MessageHandler(filters.ALL, handlers.message))

    await tg_app.initialize()
    await tg_app.start()

    scheduler = BroadcastScheduler()
    scheduler_task = asyncio.create_task(scheduler.run_forever())

    web_app = web.Application()
    setup_miniapp_routes(web_app)

    async def telegram_webhook(request: web.Request) -> web.Response:
        if settings.webhook_secret and request.headers.get('X-Telegram-Bot-Api-Secret-Token') != settings.webhook_secret:
            return web.Response(status=403)
        data = await request.json()
        update = Update.de_json(data, tg_app.bot)
        await tg_app.process_update(update)
        return web.Response(text='ok')

    web_app.router.add_post('/telegram', telegram_webhook)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, settings.web_host, settings.web_port)
    await site.start()
    await tg_app.bot.set_webhook(
        url=settings.webhook_url,
        secret_token=settings.webhook_secret or None,
        allowed_updates=['message', 'callback_query'],
    )
    logger.info(f'Account-hosted broadcast bot started on {settings.web_host}:{settings.web_port}')

    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    finally:
        await scheduler.stop()
        scheduler_task.cancel()
        await runner.cleanup()
        await tg_app.stop()
        await tg_app.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
