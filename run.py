import asyncio
import os
from pathlib import Path

from aiogram import Bot, F
from dotenv import load_dotenv

load_dotenv(encoding="utf-8-sig")
os.environ.setdefault("PUBLIC_CHANNEL_ID", "0")
os.environ.setdefault("PUBLIC_CHANNEL_URL", "https://t.me")

from app.payment_display_sanitizer import repair_payment_owner_env
repair_payment_owner_env()

from app.telegram_topic_routing import install_free_topic_routing
install_free_topic_routing()

from app.signal_code_runtime import install_two_digit_signal_codes
install_two_digit_signal_codes()

import app.main as main_module
from app.autotrade.event_time_guard import install_mt5_event_datetime_helper
from app.autotrade.result_card_guard import install_result_card_formatter
from app.ux_runtime_patch import install as install_user_ux_hardening
from app.services.chat_hygiene_runtime import install as install_chat_hygiene_runtime
from app.services.signal_channel_runtime import install as install_signal_channel_runtime
from app.services.pricing_admin_runtime import install as install_pricing_admin_runtime
from app.services.account_runtime import install as install_account_runtime
from app.services.report_runtime import install as install_report_runtime
from app.services.market_brief_service import install as install_market_brief_runtime
from app.services.market_public_channel_runtime import install as install_market_public_channel_runtime
from app.services.market_content_route_runtime import install as install_market_content_route_runtime
from app.services.open_access_runtime import install as install_open_access_runtime
from app.portal_runtime import install_nexus_hub
from app.autotrade_user_runtime import install_autotrade_user_experience
from app.autotrade_cleanup_runtime import install_autotrade_durable_cleanup
from app.customer_experience import install_customer_experience
from app.customer_menu_runtime import install_customer_menu_runtime
from app.miniapp_bot_runtime import install_miniapp_bot_runtime
from app.admin_referral_invite_runtime import install as install_admin_referral_invite
from app.growth_conversion_runtime import install as install_growth_conversion
from app.edge_analytics_runtime import install as install_edge_analytics
from app.risk_admin_runtime import install as install_risk_admin
from app.topic_admin import router as topic_admin_router
from app.content.runner import main as content_main
from app.academy.router import router as academy_router
from app.academy.runner import academy_worker

install_mt5_event_datetime_helper()
install_result_card_formatter()
install_user_ux_hardening(main_module)
install_signal_channel_runtime(main_module)
install_chat_hygiene_runtime(main_module)
install_pricing_admin_runtime(main_module)
install_account_runtime(main_module)
install_report_runtime(main_module)
install_market_brief_runtime(main_module)
install_market_public_channel_runtime(main_module)
install_market_content_route_runtime(main_module)
install_open_access_runtime(main_module)
install_nexus_hub(main_module)
install_autotrade_user_experience(main_module)
install_autotrade_durable_cleanup(main_module)

install_customer_experience(main_module)
install_customer_menu_runtime(main_module)
install_miniapp_bot_runtime(main_module)
install_admin_referral_invite(main_module)
install_growth_conversion(main_module)
install_edge_analytics(main_module)
install_risk_admin(main_module)


def _restrict_core_catchall_to_private() -> None:
    """Keep legacy cleanup for ordinary private messages without swallowing commands."""
    handlers = main_module.router.message.handlers
    found = any(
        getattr(handler.callback, "__name__", "") == "clean_unhandled_message"
        for handler in handlers
    )
    if not found:
        return

    handlers[:] = [
        handler
        for handler in handlers
        if getattr(handler.callback, "__name__", "") != "clean_unhandled_message"
    ]

    async def _private_unhandled_message(message, bot):
        await main_module.clean_unhandled_message(message, bot)

    main_module.router.message(
        F.chat.type == "private",
        F.text,
        ~F.text.startswith("/"),
    )(_private_unhandled_message)


def _promote_academy_handlers() -> None:
    """Run Academy handlers before legacy parent-router catch-alls.

    aiogram evaluates handlers attached to the current router before child
    routers. The v0.6.5 app has several legacy generic handlers, so merely
    including academy_router as a child is not sufficient for admin commands.
    Prepending Academy handlers to the core observers makes /academy_* and
    academy callbacks deterministic without changing legacy business logic.
    """
    existing_message_callbacks = {
        id(handler.callback) for handler in main_module.router.message.handlers
    }
    promoted_messages = [
        handler for handler in academy_router.message.handlers
        if id(handler.callback) not in existing_message_callbacks
    ]
    if promoted_messages:
        main_module.router.message.handlers[:0] = promoted_messages

    existing_callback_callbacks = {
        id(handler.callback) for handler in main_module.router.callback_query.handlers
    }
    promoted_callbacks = [
        handler for handler in academy_router.callback_query.handlers
        if id(handler.callback) not in existing_callback_callbacks
    ]
    if promoted_callbacks:
        main_module.router.callback_query.handlers[:0] = promoted_callbacks


_restrict_core_catchall_to_private()
_promote_academy_handlers()
main_module.router.include_router(topic_admin_router)

bot_main = main_module.main


async def _safe_content_runtime() -> None:
    try:
        await content_main()
    except asyncio.CancelledError:
        raise
    except Exception:
        main_module.log.exception(
            "[NEXUS] Agentic content runtime failed; Telegram bot remains online"
        )


async def _safe_academy_runtime() -> None:
    academy_bot = Bot(main_module.settings.bot_token)
    try:
        await academy_worker(academy_bot)
    except asyncio.CancelledError:
        raise
    except Exception:
        main_module.log.exception(
            "[NEXUS] Academy Mentor runtime failed; Telegram bot remains online"
        )
    finally:
        await academy_bot.session.close()


async def main() -> None:
    bot_task = asyncio.create_task(bot_main(), name="nexus-telegram-bot")
    content_task = asyncio.create_task(
        _safe_content_runtime(),
        name="nexus-agentic-content",
    )
    academy_task = asyncio.create_task(
        _safe_academy_runtime(),
        name="nexus-academy-mentor",
    )
    try:
        await asyncio.gather(bot_task, content_task, academy_task)
    finally:
        for task in (bot_task, content_task, academy_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(
            bot_task,
            content_task,
            academy_task,
            return_exceptions=True,
        )


_LOCK_HANDLE = None


def _acquire_single_instance_lock():
    temp_root = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".")
    lock_path = temp_root / "NEXUS_TelegramBot.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    handle = open(lock_path, "a+b")
    handle.seek(0, os.SEEK_END)

    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()

    handle.seek(0)

    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise SystemExit(
            "[NEXUS] Telegram Bot is already running on this machine. "
            "Close the existing NEXUS bot process before starting another instance."
        ) from exc

    return handle


if __name__ == "__main__":
    _LOCK_HANDLE = _acquire_single_instance_lock()
    asyncio.run(main())
