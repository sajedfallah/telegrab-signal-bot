from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from .config import settings
from .telegram_topic_routing import configured_free_topic_route

router = Router(name="nexus-free-topic-admin")


@router.message(Command("topicid", "setfreetopic"))
async def topic_id_command(message: Message, bot: Bot) -> None:
    """Show the exact community chat/topic IDs needed for FREE routing.

    This command is admin-only and must be sent from inside the target forum
    topic. It does not mutate .env at runtime; the returned values are copied to
    the server configuration and become active after the two NEXUS services are
    restarted.
    """
    if not message.from_user or message.from_user.id not in settings.admin_ids:
        return

    thread_id = message.message_thread_id
    if not thread_id:
        await bot.send_message(
            message.chat.id,
            "این دستور را داخل Topic موردنظر گروه Forum ارسال کنید.\n"
            "مثال: وارد Topic «سیگنال» شوید و /topicid را بفرستید.",
        )
        return

    current = configured_free_topic_route()
    current_text = "غیرفعال"
    if current is not None:
        current_text = f"chat={current[0]} | topic={current[1]}"

    text = (
        "✅ NEXUS Free Signal Topic\n\n"
        f"Chat ID: {message.chat.id}\n"
        f"Topic ID: {thread_id}\n\n"
        "این دو خط را در فایل .env سرور قرار بده:\n"
        f"FREE_SIGNAL_CHAT_ID={message.chat.id}\n"
        f"FREE_SIGNAL_TOPIC_ID={thread_id}\n\n"
        f"Current route: {current_text}\n\n"
        "بعد از ذخیره .env، هر دو سرویس NEXUS-Telegram-Bot و "
        "NEXUS-AutoTrade-API را Restart کن."
    )
    await bot.send_message(
        message.chat.id,
        text,
        message_thread_id=thread_id,
    )
