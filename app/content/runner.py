from __future__ import annotations

import logging
import os
import socket

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp.resolver import AsyncResolver

from ..config import settings
from .worker import content_worker

log = logging.getLogger("nexus-content-runner")


async def main() -> None:
    if not settings.content_agents_enabled:
        log.info("NEXUS Agentic Content is disabled")
        return

    session = AiohttpSession()
    if os.getenv("TELEGRAM_PUBLIC_DNS", "true").strip().lower() in {"1", "true", "yes", "on"}:
        session._connector_init["resolver"] = AsyncResolver(nameservers=["8.8.8.8", "1.1.1.1"])
        session._connector_init["family"] = socket.AF_INET

    bot = Bot(settings.bot_token, session=session)
    try:
        await content_worker(bot)
    finally:
        await bot.session.close()
