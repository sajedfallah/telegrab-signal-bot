from __future__ import annotations

"""Strict publication gate for NEXUS standalone public market news.

Policy:
- standalone news only; morning brief/ICT posts are not counted;
- maximum five news messages per local day;
- one message per configured slot;
- only very-important items are eligible;
- durable slot/day state through app_settings so restarts do not duplicate sends.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.services import market_public_channel_runtime as market_public
from app.services import professional_news_engine as pro_news

_INSTALLED = False
_SEND_LOCK = asyncio.Lock()


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.getenv(name, str(default))).strip())
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _parse_slots(raw: str | None = None) -> tuple[tuple[int, int], ...]:
    value = str(raw if raw is not None else os.getenv("NEWS_DAILY_SLOTS", "12:15,14:30,17:00,19:30,22:00"))
    slots: list[tuple[int, int]] = []
    for part in value.split(","):
        item = part.strip()
        if not item:
            continue
        try:
            hh_s, mm_s = item.split(":", 1)
            hh, mm = int(hh_s), int(mm_s)
        except Exception:
            continue
        if 0 <= hh <= 23 and 0 <= mm <= 59 and (hh, mm) not in slots:
            slots.append((hh, mm))
    slots.sort()
    return tuple(slots[:5])


def _local_now(main: Any, now_utc: datetime | None = None) -> datetime:
    now = now_utc or datetime.now(timezone.utc)
    return now.astimezone(ZoneInfo(main.settings.timezone))


def _slot_key(local_now: datetime, hh: int, mm: int) -> str:
    return f"{local_now.date().isoformat()}:{hh:02d}{mm:02d}"


def _due_slot(main: Any, now_utc: datetime | None = None) -> tuple[int, int] | None:
    local = _local_now(main, now_utc)
    window = _env_int("NEWS_SLOT_WINDOW_MINUTES", 75, 5, 180)
    for hh, mm in _parse_slots():
        scheduled = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if scheduled <= local <= scheduled + timedelta(minutes=window):
            key = _slot_key(local, hh, mm)
            if str(main.db.get_setting(f"news_slot_sent:{key}", "0")) != "1":
                return hh, mm
    return None


def _daily_count(main: Any, local_now: datetime) -> int:
    try:
        return int(main.db.get_setting(f"news_daily_count:{local_now.date().isoformat()}", "0") or 0)
    except Exception:
        return 0


def _mark_sent(main: Any, local_now: datetime, slot: tuple[int, int]) -> None:
    hh, mm = slot
    key = _slot_key(local_now, hh, mm)
    current = _daily_count(main, local_now)
    main.db.set_setting(f"news_slot_sent:{key}", "1")
    main.db.set_setting(f"news_daily_count:{local_now.date().isoformat()}", str(current + 1))


def _eligible(decision: pro_news.NewsDecision) -> bool:
    minimum = _env_int("NEWS_SLOT_MIN_SCORE", 90, 1, 100)
    allowed_tiers = {
        x.strip().upper()
        for x in os.getenv("NEWS_SLOT_ALLOWED_SOURCE_TIERS", "A,B").split(",")
        if x.strip()
    }
    return (
        decision.publish
        and decision.is_important
        and decision.score >= minimum
        and decision.source_tier.upper() in allowed_tiers
    )


def install(main: Any) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original = market_public._broadcast_news_item

    async def _quota_broadcast_news_item(runtime_main: Any, bot: Any, item: Any) -> tuple[int, int]:
        decision = pro_news.evaluate(item, main=runtime_main)

        if not _eligible(decision):
            market_public.log.info(
                "[NEXUS][NEWS_QUOTA][SUPPRESSED] story=%s score=%s category=%s tier=%s reason=not_very_important",
                decision.story_id,
                decision.score,
                decision.category,
                decision.source_tier,
            )
            return (0, 0)

        async with _SEND_LOCK:
            local = _local_now(runtime_main)
            daily_max = _env_int("NEWS_DAILY_MAX", 5, 1, 5)
            if _daily_count(runtime_main, local) >= daily_max:
                market_public.log.info(
                    "[NEXUS][NEWS_QUOTA][SUPPRESSED] story=%s score=%s reason=daily_limit",
                    decision.story_id,
                    decision.score,
                )
                return (0, 0)

            slot = _due_slot(runtime_main)
            if slot is None:
                market_public.log.info(
                    "[NEXUS][NEWS_QUOTA][SUPPRESSED] story=%s score=%s reason=outside_news_slot",
                    decision.story_id,
                    decision.score,
                )
                return (0, 0)

            sent, failed = await original(runtime_main, bot, item)
            if sent > 0:
                _mark_sent(runtime_main, local, slot)
                market_public.log.info(
                    "[NEXUS][NEWS_QUOTA][PUBLISHED] story=%s score=%s slot=%02d:%02d count=%s/%s",
                    decision.story_id,
                    decision.score,
                    slot[0],
                    slot[1],
                    _daily_count(runtime_main, local),
                    daily_max,
                )
            return sent, failed

    market_public._broadcast_news_item = _quota_broadcast_news_item
    _INSTALLED = True
    main.log.info(
        "[NEXUS][NEWS_QUOTA][INSTALLED] max_per_day=%s slots=%s min_score=%s source_tiers=%s",
        _env_int("NEWS_DAILY_MAX", 5, 1, 5),
        ",".join(f"{h:02d}:{m:02d}" for h, m in _parse_slots()),
        _env_int("NEWS_SLOT_MIN_SCORE", 90, 1, 100),
        os.getenv("NEWS_SLOT_ALLOWED_SOURCE_TIERS", "A,B"),
    )
