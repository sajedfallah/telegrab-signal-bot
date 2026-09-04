from __future__ import annotations

import functools
import inspect
import logging
import os
from typing import Any

from aiogram import Bot

from .config import settings

log = logging.getLogger("nexus.telegram-topic-routing")

# FREE remains the logical NEXUS destination everywhere in the bot, API and MT5
# contract. When the two variables below are configured, the physical Telegram
# destination is transparently remapped to one forum topic in the community.
_FREE_TOPIC_METHODS = (
    "get_chat",
    "send_message",
    "send_photo",
    "send_document",
    "send_video",
    "send_animation",
    "send_audio",
    "send_voice",
    "send_video_note",
    "send_location",
    "send_venue",
    "send_contact",
    "send_poll",
    "send_dice",
    "send_sticker",
    "send_media_group",
    "send_chat_action",
    "copy_message",
    "forward_message",
    "edit_message_text",
    "edit_message_caption",
    "edit_message_media",
    "edit_message_reply_markup",
    "delete_message",
    "delete_messages",
    "stop_poll",
    "pin_chat_message",
    "unpin_chat_message",
)


def _telegram_target(raw: str) -> int | str:
    value = str(raw or "").strip()
    if not value:
        raise ValueError("empty Telegram target")
    try:
        return int(value)
    except ValueError:
        return value


def configured_free_topic_route() -> tuple[int | str, int] | None:
    """Return (community chat, topic/thread id) when forum routing is enabled."""
    raw_chat = os.getenv("FREE_SIGNAL_CHAT_ID", "").strip()
    raw_topic = os.getenv("FREE_SIGNAL_TOPIC_ID", "").strip()
    if not raw_chat or not raw_topic:
        return None
    try:
        topic_id = int(raw_topic)
    except ValueError as exc:
        raise RuntimeError("FREE_SIGNAL_TOPIC_ID must be an integer") from exc
    if topic_id <= 0:
        raise RuntimeError("FREE_SIGNAL_TOPIC_ID must be greater than zero")
    return _telegram_target(raw_chat), topic_id


def _same_target(left: Any, right: Any) -> bool:
    return str(left).strip().casefold() == str(right).strip().casefold()


def _wrap_bot_method(method_name: str, physical_chat: int | str, topic_id: int) -> bool:
    original = getattr(Bot, method_name, None)
    if original is None or not inspect.iscoroutinefunction(original):
        return False
    if getattr(original, "__nexus_free_topic_wrapped__", False):
        return False

    signature = inspect.signature(original)
    if "chat_id" not in signature.parameters:
        return False

    @functools.wraps(original)
    async def routed(*args, **kwargs):
        bound = signature.bind_partial(*args, **kwargs)
        chat_id = bound.arguments.get("chat_id")
        if _same_target(chat_id, settings.free_channel_target):
            bound.arguments["chat_id"] = physical_chat
            # Methods that can publish into a forum topic receive the thread id.
            # Existing explicit thread routing always wins.
            if "message_thread_id" in signature.parameters and not bound.arguments.get("message_thread_id"):
                bound.arguments["message_thread_id"] = topic_id
            return await original(*bound.args, **bound.kwargs)
        return await original(*args, **kwargs)

    routed.__nexus_free_topic_wrapped__ = True
    setattr(Bot, method_name, routed)
    return True


def install_free_topic_routing() -> bool:
    """Install process-wide logical FREE -> community topic routing for aiogram Bot.

    This is intentionally installed by both run.py and run_api.py so signals
    created from the Telegram admin flow and signals created by the MT5 admin
    authority use the exact same Telegram destination and lifecycle thread.
    """
    route = configured_free_topic_route()
    if route is None:
        return False
    if getattr(Bot, "__nexus_free_topic_routing_installed__", False):
        return True

    physical_chat, topic_id = route
    wrapped = 0
    for method_name in _FREE_TOPIC_METHODS:
        if _wrap_bot_method(method_name, physical_chat, topic_id):
            wrapped += 1

    Bot.__nexus_free_topic_routing_installed__ = True
    log.info(
        "FREE Telegram destination routed to chat=%s topic=%s (%s Bot methods wrapped)",
        physical_chat,
        topic_id,
        wrapped,
    )
    return True
