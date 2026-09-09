from __future__ import annotations

import functools
import inspect
import logging

from aiogram import Bot

log = logging.getLogger("nexus.telegram_delete_guard")

PROTECTED_CHAT_IDS = {
    -1003982028478,
}

_PROTECTED_METHODS = (
    "delete_message",
    "delete_messages",
    "delete_forum_topic",
)


def _chat_id_from_call(signature, args, kwargs):
    try:
        bound = signature.bind_partial(*args, **kwargs)
        return bound.arguments.get("chat_id")
    except Exception:
        return kwargs.get("chat_id")


def _install_method_guard(method_name: str) -> bool:
    original = getattr(Bot, method_name, None)

    if original is None:
        return False

    if getattr(original, "__nexus_delete_guard__", False):
        return False

    signature = inspect.signature(original)

    @functools.wraps(original)
    async def guarded(*args, **kwargs):
        chat_id = _chat_id_from_call(signature, args, kwargs)

        try:
            normalized = int(chat_id)
        except Exception:
            normalized = chat_id

        if normalized in PROTECTED_CHAT_IDS:
            log.critical(
                "[NEXUS][DELETE_BLOCKED] method=%s chat_id=%s",
                method_name,
                chat_id,
            )
            # Pretend success so cleanup loops do not retry forever.
            return True

        return await original(*args, **kwargs)

    guarded.__nexus_delete_guard__ = True
    setattr(Bot, method_name, guarded)
    return True


def install_telegram_delete_guard() -> bool:
    installed = 0

    for method_name in _PROTECTED_METHODS:
        if _install_method_guard(method_name):
            installed += 1

    log.warning(
        "[NEXUS][DELETE_GUARD][INSTALLED] protected=%s methods=%s",
        sorted(PROTECTED_CHAT_IDS),
        installed,
    )

    return True
