from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable


log = logging.getLogger(__name__)
DEFAULT_INFO_TTL_SECONDS = 30
MIN_DELETE_DELAY_SECONDS = 3


async def delete_message_logged(bot, chat_id: int, message_id: int, *, reason: str = "lifecycle") -> bool:
    """Delete one Telegram message and record the outcome without breaking UX flows."""
    try:
        await bot.delete_message(int(chat_id), int(message_id))
        log.info(
            "Telegram message deleted: chat_id=%s message_id=%s reason=%s",
            chat_id,
            message_id,
            reason,
        )
        return True
    except Exception as exc:
        log.warning(
            "Telegram message deletion failed: chat_id=%s message_id=%s reason=%s error=%s",
            chat_id,
            message_id,
            reason,
            exc,
        )
        return False


async def delete_after(
    bot,
    chat_id: int,
    message_id: int,
    *,
    delay_seconds: int = DEFAULT_INFO_TTL_SECONDS,
    reason: str = "transient",
) -> bool:
    await asyncio.sleep(max(MIN_DELETE_DELAY_SECONDS, int(delay_seconds)))
    return await delete_message_logged(bot, chat_id, message_id, reason=reason)


def schedule_delete(
    bot,
    chat_id: int,
    message_id: int,
    *,
    delay_seconds: int = DEFAULT_INFO_TTL_SECONDS,
    reason: str = "transient",
    task_sink: set[asyncio.Task] | None = None,
) -> asyncio.Task:
    """Schedule a best-effort transient-message deletion.

    Telegram private bots have no reliable message-read receipt. NEXUS therefore
    uses deterministic time/callback semantics instead of claiming read-aware
    deletion.
    """
    task = asyncio.create_task(
        delete_after(
            bot,
            chat_id,
            message_id,
            delay_seconds=delay_seconds,
            reason=reason,
        )
    )
    if task_sink is not None:
        task_sink.add(task)
        task.add_done_callback(task_sink.discard)
    return task


async def send_transient(
    sender: Callable[..., Awaitable],
    bot,
    chat_id: int,
    text: str,
    *,
    delay_seconds: int = DEFAULT_INFO_TTL_SECONDS,
    reason: str = "informational",
    task_sink: set[asyncio.Task] | None = None,
    **send_kwargs,
):
    """Send a transient text message and schedule its deterministic deletion."""
    msg = await sender(int(chat_id), text, **send_kwargs)
    schedule_delete(
        bot,
        int(chat_id),
        int(msg.message_id),
        delay_seconds=delay_seconds,
        reason=reason,
        task_sink=task_sink,
    )
    return msg
