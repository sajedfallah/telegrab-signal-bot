from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot

from app.config import settings as core_settings

from . import repository
from .agent import AcademyMentorAgent
from .settings import academy_settings

log = logging.getLogger("nexus-academy-mentor")


def _parse_hm(value: str) -> tuple[int, int]:
    try:
        hh, mm = (int(x) for x in value.strip().split(":", 1))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    except Exception:
        pass
    return 20, 30


async def _notify_admins(bot: Bot, text: str) -> None:
    for admin_id in core_settings.admin_ids:
        try:
            await bot.send_message(int(admin_id), text)
        except Exception:
            log.exception("academy admin alert failed admin=%s", admin_id)


async def academy_worker(bot: Bot) -> None:
    if not academy_settings.enabled:
        log.info("NEXUS Academy Mentor is disabled")
        return

    repository.ensure_schema()
    agent = AcademyMentorAgent()
    tz = ZoneInfo(academy_settings.timezone)
    hour, minute = _parse_hm(academy_settings.daily_time)
    handled_dates: set[str] = set()

    while True:
        try:
            now = datetime.now(tz)
            day = now.date()
            key = day.isoformat()
            due = (now.hour, now.minute) >= (hour, minute)
            if due and key not in handled_dates:
                status = repository.status_for_day(key)
                if status not in {"published", "previewed", "cancelled"}:
                    last_error: Exception | None = None
                    for attempt in range(1, academy_settings.max_retries + 1):
                        try:
                            if academy_settings.approval_mode:
                                await agent.preview(bot, day)
                            else:
                                await agent.publish(bot, day)
                            last_error = None
                            break
                        except Exception as exc:
                            last_error = exc
                            repository.record_failure(key, f"daily_attempt_{attempt}", str(exc))
                            if attempt < academy_settings.max_retries:
                                await asyncio.sleep(min(30, attempt * 5))
                    if last_error is not None:
                        await _notify_admins(
                            bot,
                            "🚨 خطای NEXUS Academy\n\n"
                            f"درس {key} پس از {academy_settings.max_retries} تلاش آماده/منتشر نشد.\n"
                            f"خطا: {str(last_error)[:500]}\n\n"
                            f"برای تلاش دستی: /academy_preview {key}",
                        )
                handled_dates.add(key)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("academy mentor worker loop failed")
        await asyncio.sleep(20)
