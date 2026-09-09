from __future__ import annotations

import functools
import inspect
import logging
import os
import traceback

from aiogram import Bot


log = logging.getLogger("nexus.telegram_safety_guard")

PROTECTED_CHAT_ID = int(
    os.getenv("PUBLIC_CONTENT_CHAT_ID", "-1003982028478")
)

PUBLIC_TOPIC_ID = int(
    os.getenv("PUBLIC_CONTENT_TOPIC_ID", "8")
)

FREE_TOPIC_ID = int(os.getenv("FREE_SIGNAL_TOPIC_ID", "16"))


def _normalize(value):
    try:
        return int(value)
    except Exception:
        return value


def _caller_is_session_sticker() -> bool:
    """
    Detect Session Sticker code regardless of whether the local package is
    called session_sticker or session_stickers.
    """
    try:
        for frame in inspect.stack()[2:14]:
            filename = str(frame.filename or "").replace("\\", "/").lower()
            function = str(frame.function or "").lower()

            if (
                "session_sticker" in filename
                or "session-sticker" in filename
                or "session_sticker" in function
            ):
                return True
    except Exception:
        pass

    return False


def _install_delete_guard(method_name: str) -> bool:
    original = getattr(Bot, method_name, None)

    if original is None:
        return False

    if getattr(original, "__nexus_topic_delete_guard__", False):
        return False

    signature = inspect.signature(original)

    @functools.wraps(original)
    async def guarded(*args, **kwargs):
        try:
            bound = signature.bind_partial(*args, **kwargs)
            chat_id = bound.arguments.get("chat_id")
        except Exception:
            chat_id = kwargs.get("chat_id")

        if _normalize(chat_id) == PROTECTED_CHAT_ID:
            log.critical(
                "[NEXUS][TELEGRAM_DELETE_BLOCKED] "
                "method=%s chat=%s protected_public_topic=%s "
                "protected_free_topic=%s",
                method_name,
                chat_id,
                PUBLIC_TOPIC_ID,
                FREE_TOPIC_ID,
            )

            # Do NOT call Telegram.
            # Return success so legacy cleanup workers do not retry forever.
            return True

        return await original(*args, **kwargs)

    guarded.__nexus_topic_delete_guard__ = True
    setattr(Bot, method_name, guarded)
    return True


def _install_session_sticker_route_guard() -> bool:
    """
    Session Stickers are PUBLIC content.

    Even though FREE and PUBLIC share the same physical supergroup,
    Session Sticker calls are forced to PUBLIC topic 8.
    """
    original = getattr(Bot, "send_sticker", None)

    if original is None:
        return False

    if getattr(original, "__nexus_session_sticker_route_guard__", False):
        return False

    signature = inspect.signature(original)

    @functools.wraps(original)
    async def routed(*args, **kwargs):
        if not _caller_is_session_sticker():
            return await original(*args, **kwargs)

        bound = signature.bind_partial(*args, **kwargs)

        bound.arguments["chat_id"] = PROTECTED_CHAT_ID

        if "message_thread_id" in signature.parameters:
            bound.arguments["message_thread_id"] = PUBLIC_TOPIC_ID

        log.info(
            "[NEXUS][SESSION_STICKER_ROUTE] chat=%s topic=%s",
            PROTECTED_CHAT_ID,
            PUBLIC_TOPIC_ID,
        )

        return await original(*bound.args, **bound.kwargs)

    routed.__nexus_session_sticker_route_guard__ = True
    setattr(Bot, "send_sticker", routed)
    return True


def install_telegram_safety_guard() -> bool:
    delete_methods = (
        "delete_message",
        "delete_messages",
        "delete_forum_topic",
    )

    installed = 0

    for method_name in delete_methods:
        if _install_delete_guard(method_name):
            installed += 1

    sticker_guard = _install_session_sticker_route_guard()

    log.warning(
        "[NEXUS][TELEGRAM_SAFETY_GUARD][INSTALLED] "
        "chat=%s public_topic=%s free_topic=%s "
        "delete_methods=%s session_sticker_guard=%s",
        PROTECTED_CHAT_ID,
        PUBLIC_TOPIC_ID,
        FREE_TOPIC_ID,
        installed,
        sticker_guard,
    )

    return True


