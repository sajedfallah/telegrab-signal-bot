from __future__ import annotations

"""Route the logical NEXUS public destination to one Telegram forum topic."""

import functools
import inspect
import logging
import os
from datetime import date
from typing import Any

from aiogram import Bot

from app.daily_stickers import router as daily_router
from app.daily_stickers import service as daily_service
from app.services import market_public_channel_runtime as public_runtime
from app.services import morning_package_runtime as morning_runtime

log = logging.getLogger(__name__)


def _target(main: Any) -> int | str:
    raw = os.getenv("PUBLIC_CHANNEL_CHAT_ID", "").strip()
    if not raw:
        return main.settings.public_channel_id
    try:
        return int(raw)
    except ValueError:
        return raw


def _topic_id() -> int | None:
    raw = os.getenv("PUBLIC_CHANNEL_TOPIC_ID", "").strip()
    if not raw:
        return None
    value = int(raw)
    if value <= 0:
        raise RuntimeError("PUBLIC_CHANNEL_TOPIC_ID must be greater than zero")
    return value


def _same_target(left: Any, right: Any) -> bool:
    return str(left).strip().casefold() == str(right).strip().casefold()


def _wrap_public_method(method_name: str, target: int | str, topic_id: int) -> bool:
    original = getattr(Bot, method_name, None)
    if original is None or not inspect.iscoroutinefunction(original):
        return False
    if getattr(original, "__nexus_public_topic_wrapped__", False):
        return False
    signature = inspect.signature(original)
    if "chat_id" not in signature.parameters or "message_thread_id" not in signature.parameters:
        return False

    @functools.wraps(original)
    async def routed(*args, **kwargs):
        bound = signature.bind_partial(*args, **kwargs)
        chat_id = bound.arguments.get("chat_id")
        if _same_target(chat_id, target) and not bound.arguments.get("message_thread_id"):
            bound.arguments["message_thread_id"] = topic_id
            return await original(*bound.args, **bound.kwargs)
        return await original(*args, **kwargs)

    routed.__nexus_public_topic_wrapped__ = True
    setattr(Bot, method_name, routed)
    return True


def install(main: Any) -> None:
    target = _target(main)
    topic_id = _topic_id()
    if topic_id is None:
        log.info("[NEXUS][PUBLIC_TOPIC] disabled; PUBLIC_CHANNEL_TOPIC_ID is empty")
        return

    # Process-wide protection: any normal public text/photo/sticker routed to the
    # logical public chat lands in the configured forum topic.  This also covers
    # public copies of FREE/VIP reports.
    wrapped = 0
    for method_name in ("send_message", "send_photo", "send_sticker", "send_video", "send_animation", "send_document"):
        if _wrap_public_method(method_name, target, topic_id):
            wrapped += 1

    async def send_for_date_topic(bot, day: date, *, force: bool = False, store=None):
        store = store or daily_service.get_store()
        if not force and store.was_delivered(day, target):
            return False, "already_sent", None
        row = store.get_sticker(day)
        if row is None:
            return False, "missing_sticker", None
        msg = await bot.send_sticker(
            chat_id=target,
            message_thread_id=topic_id,
            sticker=str(row["file_id"]),
            disable_notification=os.getenv("DAILY_STICKER_SILENT", "false").strip().lower()
            in {"1", "true", "yes", "on"},
        )
        store.mark_delivered(day, target, int(msg.message_id))
        return True, "sent", int(msg.message_id)

    async def send_public_topic(main_arg, bot, text: str, *, reason: str, image_url: str = "") -> bool:
        if image_url:
            try:
                await bot.send_photo(
                    chat_id=target,
                    message_thread_id=topic_id,
                    photo=image_url,
                    caption=text,
                    parse_mode="HTML",
                )
                log.info("market public-topic delivery: reason=%s target=%s topic=%s status=sent_with_image", reason, target, topic_id)
                return True
            except Exception as exc:
                log.info("market public-topic image unavailable; fallback to text: reason=%s target=%s topic=%s error=%s", reason, target, topic_id, exc)
        try:
            await bot.send_message(
                chat_id=target,
                message_thread_id=topic_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            log.info("market public-topic delivery: reason=%s target=%s topic=%s status=sent", reason, target, topic_id)
            return True
        except Exception as exc:
            log.warning("market public-topic delivery failed: reason=%s target=%s topic=%s error=%s", reason, target, topic_id, exc)
            return False

    # Patch imported bindings that were captured before this runtime installed.
    daily_service.send_for_date = send_for_date_topic
    daily_service.target_chat = lambda: target
    daily_router.send_for_date = send_for_date_topic
    daily_router.target_chat = lambda: target
    morning_runtime.send_for_date = send_for_date_topic
    public_runtime._send_public = send_public_topic

    log.info(
        "[NEXUS][PUBLIC_TOPIC][INSTALLED] target=%s topic=%s wrapped=%s morning=daily-sticker+brief+gold+btc",
        target,
        topic_id,
        wrapped,
    )
