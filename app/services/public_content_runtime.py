from __future__ import annotations

"""Deterministic public-channel content scheduler for NEXUS.

This runtime intentionally stays separate from the legacy Agentic Content pipeline.
It complements the existing Market Public Channel runtime with one curated Quick Tip
per day while preserving the five-category public-channel model:

    daily_analysis / quick_tip / market_news / important_news / news_alert

Morning analysis and event-driven news remain owned by market_public_channel_runtime.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo


log = logging.getLogger(__name__)


_QUICK_TIPS: tuple[tuple[str, str, str], ...] = (
    (
        "Liquidity Sweep ≠ Entry",
        "گرفتن نقدینگی به‌تنهایی دلیل ورود نیست. بعد از Sweep منتظر واکنش قیمت و تأیید معتبر روی تایم ورود بمان.",
        "Liquidity → Reaction → Confirmation → Entry",
    ),
    (
        "FVG بدون Context کافی نیست",
        "هر Fair Value Gap ارزش معامله ندارد. FVG زمانی مهم‌تر است که با Bias تایم بالاتر و نقدینگی هم‌جهت باشد.",
        "Context → Liquidity → FVG → Confirmation",
    ),
    (
        "اول Bias، بعد Entry",
        "قبل از جست‌وجوی ورود روی 5M، جهت و ساختار 1H را مشخص کن. ورود دقیق بدون Context می‌تواند فقط یک معامله تصادفی باشد.",
        "1H Context → 15M Zone → 5M Trigger",
    ),
    (
        "Decision Point را تعقیب نکن",
        "اگر قیمت از ناحیه اصلی حرکت کرده و Entry از دست رفته، دنبال قیمت نرو. منتظر Retest یا ستاپ جدید بمان.",
        "Missed Entry → No Chase → Wait for New Setup",
    ),
    (
        "Stop پشت ساختار قرار می‌گیرد",
        "حد ضرر را صرفاً با عدد ثابت انتخاب نکن. Invalid شدن ایده معاملاتی باید محل Stop را تعیین کند.",
        "Invalidation First → Stop Placement Second",
    ),
    (
        "خبر مهم = صبر بیشتر",
        "اطراف CPI، NFP، FOMC و سخنرانی‌های مهم، اسپرد و نوسان می‌تواند غیرعادی شود. ورود بدون تأیید ریسک اجرا را بالا می‌برد.",
        "High Impact News → Wait → Reprice → Confirm",
    ),
    (
        "MSS باید معنی داشته باشد",
        "هر شکست کوچک ساختار Market Structure Shift نیست. MSS معتبر باید بعد از گرفتن نقدینگی و با Displacement واضح دیده شود.",
        "Liquidity → Displacement → MSS",
    ),
    (
        "ریسک ثابت، تصمیم بهتر",
        "وقتی درصد ریسک از قبل مشخص باشد، کیفیت ستاپ را با اندازه پوزیشن اشتباه نمی‌گیری و تصمیم‌گیری احساسی کمتر می‌شود.",
        "Fixed Risk → Consistent Execution",
    ),
    (
        "Premium / Discount را با Range درست بسنج",
        "Premium و Discount فقط وقتی معنا دارد که dealing range منطقی انتخاب شده باشد. Range اشتباه، ناحیه ورود را هم اشتباه می‌کند.",
        "Valid Range → Premium/Discount → Setup",
    ),
    (
        "Confirmation قبل از Prediction",
        "کار معامله‌گر پیش‌بینی هر حرکت نیست. سناریو را مشخص کن و فقط وقتی بازار آن را تأیید کرد اجرا کن.",
        "Scenario → Confirmation → Execution",
    ),
)


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "true" if default else "false")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.getenv(name, str(default))).strip())
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _parse_hm(value: str, default: str = "13:30") -> tuple[int, int]:
    raw = str(value or default).strip()
    try:
        hh_s, mm_s = raw.split(":", 1)
        hh, mm = int(hh_s), int(mm_s)
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    except Exception:
        pass
    return (13, 30)


def _public_target(main: Any) -> Any:
    # Public-content routing must prefer the forum-supergroup target.
    # Legacy PUBLIC_CHANNEL_ID remains only as fallback compatibility.
    raw = os.getenv("PUBLIC_CONTENT_CHAT_ID", "").strip()
    if raw and raw not in {"0", "None"}:
        return int(raw)

    target = getattr(main.settings, "public_channel_id", None)
    if target is None or str(target).strip() in {"", "0", "None"}:
        raise RuntimeError("NEXUS public channel is not configured")
    return target


def _public_topic_id() -> int | None:
    raw = os.getenv("PUBLIC_CONTENT_TOPIC_ID", "").strip()
    if not raw or raw in {"0", "None"}:
        return None
    topic_id = int(raw)
    return topic_id if topic_id > 0 else None


def _tip_for_date(local_now: datetime) -> tuple[str, str, str]:
    # Stable deterministic rotation: a restart never changes today's selected tip.
    index = local_now.date().toordinal() % len(_QUICK_TIPS)
    return _QUICK_TIPS[index]


def render_quick_tip(local_now: datetime) -> str:
    title, body, rule = _tip_for_date(local_now)
    return (
        "<b>💡 NEXUS | QUICK TIP</b>\n\n"
        f"<b>{title}</b>\n\n"
        f"{body}\n\n"
        "<b>📌 Rule</b>\n"
        f"<code>{rule}</code>"
    )


async def _publish_quick_tip(main: Any, bot: Any, local_now: datetime) -> bool:
    text = render_quick_tip(local_now)
    try:
        await bot.send_message(
            _public_target(main),
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            message_thread_id=_public_topic_id(),
        )
        log.info(
            "[NEXUS][PUBLIC_CONTENT][PUBLISHED] category=quick_tip date=%s",
            local_now.date().isoformat(),
        )
        return True
    except Exception as exc:
        log.warning("[NEXUS][PUBLIC_CONTENT][FAILED] category=quick_tip error=%s", exc)
        return False


async def public_content_worker(bot: Any, main: Any) -> None:
    """Publish one high-value Quick Tip per local day.

    The existing market runtime already owns Daily Analysis and event-driven news.
    This worker deliberately does not manufacture filler content and does not add
    any sixth category.
    """
    tz = ZoneInfo(main.settings.timezone)

    while True:
        try:
            if _env_bool("NEXUS_PUBLIC_CONTENT_ENABLED", True) and _env_bool("NEXUS_QUICK_TIP_ENABLED", True):
                now_utc = datetime.now(timezone.utc)
                local_now = now_utc.astimezone(tz)
                hh, mm = _parse_hm(os.getenv("NEXUS_QUICK_TIP_TIME", "13:30"))
                scheduled = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                catchup_hours = _env_int("NEXUS_QUICK_TIP_CATCHUP_HOURS", 4, 1, 12)
                due = scheduled <= local_now <= scheduled + timedelta(hours=catchup_hours)
                today = local_now.date().isoformat()
                last_date = str(main.db.get_setting("public_quick_tip_last_date", "") or "").strip()

                if due and last_date != today:
                    if await _publish_quick_tip(main, bot, local_now):
                        main.db.set_setting("public_quick_tip_last_date", today)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("[NEXUS][PUBLIC_CONTENT][WORKER_FAILURE]")

        await asyncio.sleep(30)


def install(main: Any) -> None:
    """Attach Quick Tip scheduling to the existing durable report worker."""
    original_report_worker = main.report_worker

    async def report_market_and_public_content_worker(bot: Any) -> None:
        core_task = asyncio.create_task(original_report_worker(bot), name="nexus-report-market-worker")
        content_task = asyncio.create_task(public_content_worker(bot, main), name="nexus-public-content-worker")
        try:
            await asyncio.gather(core_task, content_task)
        finally:
            for task in (core_task, content_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(core_task, content_task, return_exceptions=True)

    main.report_worker = report_market_and_public_content_worker
    log.info(
        "[NEXUS][PUBLIC_CONTENT][INSTALLED] categories=daily_analysis,quick_tip,market_news,important_news,news_alert quick_tip=%s time=%s legacy_agentic_independent=true",
        _env_bool("NEXUS_QUICK_TIP_ENABLED", True),
        os.getenv("NEXUS_QUICK_TIP_TIME", "13:30"),
    )
