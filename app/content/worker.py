from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot

from ..config import settings
from . import repository
from .pipeline import ContentPipeline

log = logging.getLogger("nexus-content-worker")


def _parse_hm(value: str) -> tuple[int, int]:
    try:
        hour, minute = (int(item) for item in value.strip().split(":", 1))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except Exception:
        pass
    return 12, 0


async def content_worker(bot: Bot) -> None:
    if not settings.content_agents_enabled:
        log.info("Agentic channel content is disabled")
        return

    timezone = ZoneInfo(settings.timezone)
    hour, minute = _parse_hm(settings.content_daily_time)
    pipeline = ContentPipeline()
    repository.ensure_schema()
    log.info(
        "Agentic content enabled: daily=%s approval_mode=%s target=%s provider=%s model=%s",
        settings.content_daily_time,
        settings.content_approval_mode,
        settings.public_channel_id,
        settings.content_ai_provider,
        settings.content_text_model,
    )

    while True:
        try:
            now = datetime.now(timezone)
            scheduled_date = now.date().isoformat()
            due = now.hour == hour and now.minute == minute
            catchup_due = settings.content_catchup_enabled and (now.hour, now.minute) > (hour, minute)
            if due or (catchup_due and repository.status_for_day(scheduled_date) is None):
                await pipeline.run_day(bot, scheduled_date)
        except Exception:
            log.exception("content worker error")
        await asyncio.sleep(20)
