from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot

from app.config import settings
from .service import catchup_minutes, enabled, scheduled_time, send_for_date
from .storage import get_store

log = logging.getLogger("nexus.daily_stickers")


async def main() -> None:
    if not enabled():
        log.info("Daily sticker automation disabled (DAILY_STICKERS_ENABLED=false)")
        return

    get_store().init_db()
    hour, minute = scheduled_time()
    tz = ZoneInfo(settings.timezone)
    bot = Bot(settings.bot_token)
    log.info("Daily sticker automation enabled: %02d:%02d %s", hour, minute, settings.timezone)

    try:
        while True:
            now = datetime.now(tz)
            scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            deadline = scheduled + timedelta(minutes=catchup_minutes())
            if scheduled <= now <= deadline:
                try:
                    sent, reason, message_id = await send_for_date(bot, now.date())
                    if sent:
                        log.info("Daily sticker sent for %s message_id=%s", now.date(), message_id)
                    elif reason == "missing_sticker":
                        log.warning("No daily sticker configured for %s", now.date())
                except Exception:
                    log.exception("Daily sticker delivery failed for %s", now.date())
            await asyncio.sleep(30)
    finally:
        await bot.session.close()
