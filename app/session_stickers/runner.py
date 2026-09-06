from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot

from app.config import settings
from .service import due_now, enabled, events, send_event
from .storage import get_store

log = logging.getLogger("nexus.session_stickers")


async def main() -> None:
    if not enabled():
        log.info("Session sticker automation disabled (SESSION_STICKERS_ENABLED=false)")
        return

    get_store().init_db()
    bot = Bot(settings.bot_token)
    log.info("Session sticker automation enabled")
    try:
        while True:
            now_utc = datetime.now(timezone.utc)
            for event in events():
                due, local_date = due_now(event, now_utc)
                if not due:
                    continue
                try:
                    sent, reason, message_id = await send_event(bot, event.key, local_date=local_date)
                    if sent:
                        log.info("Session sticker sent event=%s date=%s message_id=%s", event.key, local_date, message_id)
                    elif reason == "missing_sticker":
                        log.warning("Session sticker missing event=%s", event.key)
                except Exception:
                    log.exception("Session sticker delivery failed event=%s", event.key)
            await asyncio.sleep(30)
    finally:
        await bot.session.close()
