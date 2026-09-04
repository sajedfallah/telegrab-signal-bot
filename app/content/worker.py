from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot

from ..config import settings as core_settings
from . import repository
from .pipeline import ContentPipeline
from .settings import content_settings

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
    if not content_settings.enabled:
        log.info("Agentic channel content is disabled")
        return

    timezone = ZoneInfo(core_settings.timezone)
    hour, minute = _parse_hm(content_settings.daily_time)
    pipeline = ContentPipeline()
    repository.ensure_schema()
    log.info(
        "Agentic content enabled: daily=%s approval_mode=%s target=%s provider=%s model=%s",
        content_settings.daily_time,
        content_settings.approval_mode,
        core_settings.public_channel_id,
        content_settings.ai_provider,
        content_settings.text_model,
    )

    while True:
        try:
            now = datetime.now(timezone)
            scheduled_date = now.date().isoformat()
            due = now.hour == hour and now.minute == minute
            catchup_due = content_settings.catchup_enabled and (now.hour, now.minute) > (hour, minute)
            if due or (catchup_due and repository.status_for_day(scheduled_date) is None):
                await pipeline.run_day(bot, scheduled_date)
        except Exception:
            log.exception("content worker error")
        await asyncio.sleep(20)
