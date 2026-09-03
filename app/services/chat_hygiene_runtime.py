from __future__ import annotations

"""Private-chat hygiene for the NEXUS Telegram dashboard.

Product policy:
* The current dashboard/menu message stays visible until the next dashboard is rendered.
* Previously tracked private bot text messages are removed when the next dashboard opens.
* Processed user *text* input is removed after its handler finishes successfully.
* Media/documents/receipts are not auto-deleted by this layer.
* Channel/group traffic is never touched.

Telegram bots cannot enumerate arbitrary chat history, so this layer only deletes
message IDs that NEXUS actually knows (tracked runtime messages plus the durable
``last_menu_message_id``). Historical messages from before deployment may remain.
"""

import logging
from collections import defaultdict
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.enums import ChatType, ParseMode
from aiogram.types import Message, TelegramObject

from .message_lifecycle import delete_message_logged


log = logging.getLogger(__name__)
_INSTALLED = False
_ORIGINAL_SEND_MESSAGE = None
_TRACKED_PRIVATE_MESSAGES: dict[int, set[int]] = defaultdict(set)


def _private_chat_id(chat_id: Any) -> int | None:
    """Return a positive numeric Telegram private-chat id, otherwise ``None``."""
    try:
        value = int(chat_id)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _remember_private_message(chat_id: Any, message_id: Any) -> None:
    cid = _private_chat_id(chat_id)
    if cid is None:
        return
    try:
        mid = int(message_id)
    except (TypeError, ValueError):
        return
    if mid > 0:
        _TRACKED_PRIVATE_MESSAGES[cid].add(mid)


def _forget_private_message(chat_id: Any, message_id: Any) -> None:
    cid = _private_chat_id(chat_id)
    if cid is None:
        return
    try:
        mid = int(message_id)
    except (TypeError, ValueError):
        return
    bucket = _TRACKED_PRIVATE_MESSAGES.get(cid)
    if not bucket:
        return
    bucket.discard(mid)
    if not bucket:
        _TRACKED_PRIVATE_MESSAGES.pop(cid, None)


async def _purge_known_private_text(main: Any, bot: Any, user_id: int, chat_id: int) -> int:
    """Delete every known prior private text/dashboard message for this chat."""
    cid = _private_chat_id(chat_id)
    if cid is None:
        return 0

    ids = set(_TRACKED_PRIVATE_MESSAGES.get(cid, set()))
    try:
        user = main.db.get_user(int(user_id))
        old_id = user["last_menu_message_id"] if user else None
        if old_id:
            ids.add(int(old_id))
    except Exception as exc:
        log.warning("chat hygiene could not read last menu id: user=%s error=%s", user_id, exc)

    deleted = 0
    for mid in sorted(ids):
        ok = await delete_message_logged(bot, cid, mid, reason="chat_hygiene_replaced")
        if ok:
            deleted += 1
        # Forget even on a best-effort Telegram failure; repeatedly retrying an old
        # inaccessible message on every navigation would create noisy logs/flooding.
        _forget_private_message(cid, mid)
    return deleted


async def _screen(main: Any, bot: Any, user_id: int, chat_id: int, text: Any, markup=None) -> None:
    """Render one canonical dashboard after cleaning all known prior private text."""
    if isinstance(text, (tuple, list)):
        text = "".join(str(x) for x in text)
    elif not isinstance(text, str):
        text = str(text)

    await _purge_known_private_text(main, bot, int(user_id), int(chat_id))

    msg = await bot.send_message(
        int(chat_id),
        text,
        reply_markup=markup,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    _remember_private_message(chat_id, msg.message_id)
    main.db.set_last_menu_message(int(user_id), int(msg.message_id))


class _ProcessedPrivateTextCleanupMiddleware(BaseMiddleware):
    """Remove user text after successful handling; preserve photos/docs/receipts."""

    async def __call__(self, handler, event: TelegramObject, data: dict[str, Any]):
        result = await handler(event, data)
        if not isinstance(event, Message):
            return result
        if event.chat.type != ChatType.PRIVATE or event.text is None:
            return result
        bot = data.get("bot")
        if bot is None:
            return result
        await delete_message_logged(
            bot,
            int(event.chat.id),
            int(event.message_id),
            reason="user_text_processed",
        )
        return result


def _install_send_message_tracking() -> None:
    global _ORIGINAL_SEND_MESSAGE
    if getattr(Bot.send_message, "_nexus_chat_hygiene", False):
        return

    _ORIGINAL_SEND_MESSAGE = Bot.send_message
    original = _ORIGINAL_SEND_MESSAGE

    async def tracked_send_message(self, chat_id, text, *args, **kwargs):
        msg = await original(self, chat_id, text, *args, **kwargs)
        _remember_private_message(chat_id, getattr(msg, "message_id", None))
        return msg

    tracked_send_message._nexus_chat_hygiene = True  # type: ignore[attr-defined]
    tracked_send_message._nexus_chat_hygiene_original = original  # type: ignore[attr-defined]
    Bot.send_message = tracked_send_message  # type: ignore[method-assign]


def install(main: Any) -> None:
    """Install deterministic single-screen hygiene without touching channel/media traffic."""
    global _INSTALLED
    if _INSTALLED:
        return

    _install_send_message_tracking()
    main.screen = lambda bot, user_id, chat_id, text, markup=None: _screen(
        main, bot, user_id, chat_id, text, markup
    )
    main._chat_hygiene_purge = lambda bot, user_id, chat_id: _purge_known_private_text(
        main, bot, user_id, chat_id
    )
    main.router.message.outer_middleware.register(_ProcessedPrivateTextCleanupMiddleware())

    _INSTALLED = True
    log.info(
        "[NEXUS][CHAT_HYGIENE][INSTALLED] single-screen=true processed-user-text-delete=true media-preserved=true"
    )
