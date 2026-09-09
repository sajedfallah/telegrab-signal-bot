import asyncio
from aiogram import Bot
import os
from pathlib import Path

from aiogram import F
from dotenv import load_dotenv

load_dotenv(encoding="utf-8-sig")
os.environ.setdefault("PUBLIC_CHANNEL_ID", "0")
os.environ.setdefault("PUBLIC_CHANNEL_URL", "https://t.me")

from app.payment_display_sanitizer import repair_payment_owner_env
repair_payment_owner_env()

from app.telegram_topic_routing import install_free_topic_routing
from app.telegram_safety_guard import install_telegram_safety_guard
from app.telegram_delete_guard import install_telegram_delete_guard
install_free_topic_routing()
install_telegram_safety_guard()
install_telegram_delete_guard()

from app.signal_code_runtime import install_two_digit_signal_codes
install_two_digit_signal_codes()

import app.main as main_module
from app.autotrade.event_time_guard import install_mt5_event_datetime_helper
from app.autotrade.result_card_guard import install_result_card_formatter
from app.ux_runtime_patch import install as install_user_ux_hardening
from app.services.chat_hygiene_runtime import install as install_chat_hygiene_runtime
from app.services.signal_channel_runtime import install as install_signal_channel_runtime
from app.services.commercial_pricing_runtime import install as install_commercial_pricing_runtime
from app.services.pricing_admin_runtime import install as install_pricing_admin_runtime
from app.services.account_runtime import install as install_account_runtime
from app.services.report_runtime import install as install_report_runtime
from app.services.market_brief_service import install as install_market_brief_runtime
from app.services.market_public_channel_runtime import install as install_market_public_channel_runtime
from app.services.news_quota_runtime import install as install_news_quota_runtime
from app.services.public_content_runtime import install as install_public_content_runtime
from app.services.performance_marketing_runtime import install as install_performance_marketing_runtime
from app.services.market_content_route_runtime import install as install_market_content_route_runtime
from app.services.open_access_runtime import install as install_open_access_runtime
from app.portal_runtime import install_nexus_hub
from app.autotrade_user_runtime import install_autotrade_user_experience
from app.autotrade_cleanup_runtime import install_autotrade_durable_cleanup
from app.customer_experience import install_customer_experience
from app.customer_menu_runtime import install_customer_menu_runtime
from app.admin_referral_invite_runtime import install as install_admin_referral_invite
from app.growth_conversion_runtime import install as install_growth_conversion
from app.edge_analytics_runtime import install as install_edge_analytics
from app.risk_admin_runtime import install as install_risk_admin
from app.topic_admin import router as topic_admin_router
from app.content.runner import main as content_main
from app.analysis_quadrant_patch import install_quadrant_rules
from app.analysis_center import install_analysis_center, router as analysis_center_router
from app.daily_stickers.router import router as daily_sticker_router
from app.session_stickers.router import router as session_sticker_router
from app.daily_stickers.runner import main as daily_sticker_main
from app.session_stickers.runner import main as session_sticker_main
from app.academy.router import router as academy_router
from app.academy.runner import academy_worker
from app.academy.caption_guard_runtime import install as install_academy_caption_guard

install_mt5_event_datetime_helper()
install_result_card_formatter()
install_user_ux_hardening(main_module)
install_signal_channel_runtime(main_module)
install_chat_hygiene_runtime(main_module)
install_commercial_pricing_runtime(main_module)
install_pricing_admin_runtime(main_module)
install_account_runtime(main_module)
install_report_runtime(main_module)
install_market_brief_runtime(main_module)
install_market_public_channel_runtime(main_module)
install_news_quota_runtime(main_module)
install_public_content_runtime(main_module)
install_performance_marketing_runtime(main_module)
install_market_content_route_runtime(main_module)
install_open_access_runtime(main_module)
install_nexus_hub(main_module)
install_autotrade_user_experience(main_module)
install_autotrade_durable_cleanup(main_module)

install_customer_experience(main_module)
install_customer_menu_runtime(main_module)
install_admin_referral_invite(main_module)
install_growth_conversion(main_module)
install_edge_analytics(main_module)
install_risk_admin(main_module)

# NEXUS Analysis Center
install_quadrant_rules()
install_analysis_center(main_module)
install_academy_caption_guard()


def _restrict_core_catchall_to_private() -> None:
    """Keep the legacy unhandled-message cleanup private-chat only.

    app.main registers clean_unhandled_message as an unfiltered parent-router
    handler. Even though its callback returns immediately for groups, aiogram
    still considers the update handled and therefore never propagates forum
    commands to child routers. Re-registering that handler with an explicit
    private-chat filter preserves chat hygiene while allowing /topicid and
    /setfreetopic to reach the forum admin router.
    """
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

    main_module.router.message(F.chat.type == "private")(_private_unhandled_message)


_restrict_core_catchall_to_private()


def _promote_analysis_message_handlers() -> None:
    """Run Analysis Center FSM handlers before the private catch-all.

    Analysis Center remains a child router for callback queries, but its
    stateful message handlers must execute in the parent observer because the
    legacy private catch-all otherwise consumes photos/text before child-router
    propagation.
    """
    source = analysis_center_router.message.handlers
    if not source:
        return

    promoted = list(source)

    # Defensive idempotency: remove any prior promoted Analysis handlers.
    main_module.router.message.handlers[:] = [
        handler
        for handler in main_module.router.message.handlers
        if getattr(handler.callback, "__module__", "") != "app.analysis_center"
    ]

    # Highest message priority; each Analysis handler still retains its own
    # FSM/content filters (waiting_h1 + photo, waiting_m15 + photo, etc.).
    main_module.router.message.handlers[0:0] = promoted

    # Prevent duplicate execution through the child router.
    source.clear()


_promote_analysis_message_handlers()


def _promote_daily_sticker_message_handlers() -> None:
    """Run Daily Sticker admin handlers before the private catch-all."""
    source = daily_sticker_router.message.handlers
    if not source:
        return

    promoted = list(source)

    main_module.router.message.handlers[:] = [
        handler
        for handler in main_module.router.message.handlers
        if getattr(handler.callback, "__module__", "") != "app.daily_stickers.router"
    ]

    main_module.router.message.handlers[0:0] = promoted

    # Prevent duplicate child-router dispatch.
    source.clear()



def _promote_session_sticker_message_handlers() -> None:
    """Run Session Sticker admin handlers before the private catch-all."""
    source = session_sticker_router.message.handlers

    if not source:
        return

    promoted = list(source)

    main_module.router.message.handlers[:] = [
        handler
        for handler in main_module.router.message.handlers
        if getattr(
            handler.callback,
            "__module__",
            "",
        ) != "app.session_stickers.router"
    ]

    main_module.router.message.handlers[0:0] = promoted

    # Prevent duplicate execution through child router.
    source.clear()


_promote_daily_sticker_message_handlers()
_promote_session_sticker_message_handlers()

main_module.router.include_router(topic_admin_router)
main_module.router.include_router(analysis_center_router)
main_module.router.include_router(daily_sticker_router)
main_module.router.include_router(session_sticker_router)
main_module.router.include_router(academy_router)

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
    bot_task = asyncio.create_task(
        bot_main(),
        name="nexus-telegram-bot",
    )

    content_task = asyncio.create_task(
        _safe_content_runtime(),
        name="nexus-agentic-content",
    )

    daily_sticker_task = asyncio.create_task(
        daily_sticker_main(),
        name="nexus-daily-stickers",
    )

    session_sticker_task = asyncio.create_task(
        session_sticker_main(),
        name="nexus-session-stickers",
    )

    academy_task = asyncio.create_task(
        _safe_academy_runtime(),
        name="nexus-academy-mentor",
    )

    tasks = (
        bot_task,
        content_task,
        daily_sticker_task,
        session_sticker_task,
        academy_task,
    )

    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()

        await asyncio.gather(
            *tasks,
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


