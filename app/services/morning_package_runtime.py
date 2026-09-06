from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.daily_stickers.service import enabled as daily_stickers_enabled
from app.daily_stickers.service import send_for_date
from app.services import market_brief_service as market

log = logging.getLogger(__name__)


async def _send_sticker_first(main: Any, bot: Any, now_utc: datetime) -> bool:
    if not daily_stickers_enabled():
        log.warning("[NEXUS][MORNING_8AM] daily sticker disabled; continuing with 3 public posts")
        return True
    day = now_utc.astimezone(ZoneInfo(main.settings.timezone)).date()
    try:
        sent, reason, message_id = await send_for_date(bot, day)
    except Exception:
        log.exception("[NEXUS][MORNING_8AM] sticker delivery failed for %s", day)
        return False
    if sent:
        log.info("[NEXUS][MORNING_8AM] sticker sent day=%s message_id=%s", day, message_id)
        await asyncio.sleep(2)
        return True
    if reason == "already_sent":
        return True
    if reason == "missing_sticker":
        log.error("[NEXUS][MORNING_8AM] sticker missing for %s; morning package paused", day)
        return False
    log.error("[NEXUS][MORNING_8AM] sticker not sent day=%s reason=%s", day, reason)
    return False


def install(main: Any) -> None:
    """Guarantee morning order: 08:00 sticker, then existing 3-message public suite."""
    original_broadcast = market._broadcast_brief

    async def sticker_first_broadcast(main_arg: Any, bot: Any, events, news, now_utc: datetime):
        if not await _send_sticker_first(main_arg, bot, now_utc):
            return (0, 1)
        return await original_broadcast(main_arg, bot, events, news, now_utc)

    market._broadcast_brief = sticker_first_broadcast
    log.info("[NEXUS][MORNING_8AM][INSTALLED] order=sticker->morning_brief->gold_map->btc_map time=08:00")
