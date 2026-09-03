from __future__ import annotations

import asyncio
import html
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Iterable, TypeVar

from aiogram.types import FSInputFile

from .message_lifecycle import schedule_delete


log = logging.getLogger(__name__)
T = TypeVar("T")
PACKAGE_MESSAGE_TTL_SECONDS = 60


@dataclass(frozen=True)
class DeliveryReport:
    ex5_sent: bool
    video_sent: bool


class AutoTradeDeliveryError(RuntimeError):
    def __init__(self, stage: str, message: str, *, ex5_sent: bool = False, video_sent: bool = False):
        super().__init__(message)
        self.stage = stage
        self.ex5_sent = ex5_sent
        self.video_sent = video_sent


async def _retry(
    label: str,
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay_seconds: float = 1.0,
) -> T:
    tries = max(1, int(attempts))
    last_error: Exception | None = None
    for attempt in range(1, tries + 1):
        try:
            return await operation()
        except Exception as exc:  # Telegram/network exceptions are intentionally retried here.
            last_error = exc
            log.warning(
                "AutoTrade delivery attempt failed: stage=%s attempt=%s/%s error=%s",
                label,
                attempt,
                tries,
                exc,
            )
            if attempt < tries:
                await asyncio.sleep(max(0.0, float(base_delay_seconds)) * (2 ** (attempt - 1)))
    assert last_error is not None
    raise last_error


async def _alert_admins(bot, admin_ids: Iterable[int], *, user_id: int, stage: str, error: Exception) -> None:
    safe_error = html.escape(str(error)[:500])
    text = (
        "⚠️ <b>NEXUS AutoTrade delivery failure</b>\n"
        f"User: <code>{int(user_id)}</code>\n"
        f"Stage: <code>{html.escape(stage)}</code>\n"
        f"Error: <code>{safe_error}</code>"
    )
    for admin_id in tuple(admin_ids):
        try:
            await bot.send_message(int(admin_id), text, parse_mode="HTML")
        except Exception as exc:
            log.warning("Could not alert admin %s about AutoTrade delivery failure: %s", admin_id, exc)


def _expire_delivery_message(bot, user_id: int, message, *, stage: str) -> None:
    """Expire an EX5/guide delivery exactly one minute after successful send."""
    message_id = getattr(message, "message_id", None)
    if message_id is None:
        log.warning(
            "AutoTrade delivery message has no message_id; cleanup not scheduled: user_id=%s stage=%s",
            user_id,
            stage,
        )
        return
    schedule_delete(
        bot,
        int(user_id),
        int(message_id),
        delay_seconds=PACKAGE_MESSAGE_TTL_SECONDS,
        reason=f"autotrade_{stage}_expired",
    )
    log.info(
        "AutoTrade delivery cleanup scheduled: user_id=%s stage=%s message_id=%s ttl=%ss",
        user_id,
        stage,
        message_id,
        PACKAGE_MESSAGE_TTL_SECONDS,
    )


async def deliver_mt5_package(
    bot,
    user_id: int,
    *,
    ex5_path: str | Path,
    guide_video_path: str | Path,
    admin_ids: Iterable[int] = (),
    lang: str = "fa",
    attempts: int = 3,
    base_delay_seconds: float = 1.0,
) -> DeliveryReport:
    """Deliver the customer MT5 package in strict EX5 -> guide-video order.

    Successful EX5 and installation-guide messages are transient and are deleted
    from the user's private chat 60 seconds after each successful Telegram send.
    This function has no license/database side effects. A Telegram delivery
    failure must never revoke or roll back an issued license.
    """
    uid = int(user_id)
    ex5 = Path(ex5_path)
    guide = Path(guide_video_path)

    if not ex5.is_file():
        exc = FileNotFoundError(f"AutoTrade EX5 release not found: {ex5}")
        await _alert_admins(bot, admin_ids, user_id=uid, stage="ex5_missing", error=exc)
        raise AutoTradeDeliveryError("ex5_missing", str(exc)) from exc

    async def send_ex5():
        caption = (
            "📥 فایل رسمی NEXUS AutoTrade برای MetaTrader 5"
            if lang == "fa"
            else "📥 Official NEXUS AutoTrade file for MetaTrader 5"
        )
        return await bot.send_document(
            uid,
            document=FSInputFile(ex5, filename="NEXUS_AutoTrade.ex5"),
            caption=caption,
            protect_content=True,
        )

    try:
        ex5_message = await _retry("ex5", send_ex5, attempts=attempts, base_delay_seconds=base_delay_seconds)
        _expire_delivery_message(bot, uid, ex5_message, stage="ex5")
    except Exception as exc:
        await _alert_admins(bot, admin_ids, user_id=uid, stage="ex5", error=exc)
        raise AutoTradeDeliveryError("ex5", str(exc)) from exc

    if not guide.is_file():
        exc = FileNotFoundError(f"AutoTrade installation guide video not found: {guide}")
        await _alert_admins(bot, admin_ids, user_id=uid, stage="guide_video_missing", error=exc)
        raise AutoTradeDeliveryError("guide_video_missing", str(exc), ex5_sent=True) from exc

    async def send_video():
        caption = (
            "🎓 راهنمای نصب و فعال‌سازی NEXUS AutoTrade در MetaTrader 5"
            if lang == "fa"
            else "🎓 NEXUS AutoTrade installation and activation guide for MetaTrader 5"
        )
        return await bot.send_video(
            uid,
            video=FSInputFile(guide),
            caption=caption,
            supports_streaming=True,
            protect_content=True,
        )

    try:
        guide_message = await _retry("guide_video", send_video, attempts=attempts, base_delay_seconds=base_delay_seconds)
        _expire_delivery_message(bot, uid, guide_message, stage="guide_video")
    except Exception as exc:
        await _alert_admins(bot, admin_ids, user_id=uid, stage="guide_video", error=exc)
        raise AutoTradeDeliveryError("guide_video", str(exc), ex5_sent=True) from exc

    log.info("AutoTrade MT5 package delivered: user_id=%s ex5=%s guide=%s", uid, ex5, guide)
    return DeliveryReport(ex5_sent=True, video_sent=True)
