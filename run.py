import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

# Load the real VPS environment before importing app.config. The historical
# PUBLIC_CHANNEL_* fields are still present in the legacy Settings schema, but
# the channel itself is retired and no longer gates bot access. Safe inert
# defaults let deployments remove those obsolete .env entries without breaking
# process startup; open_access_runtime ensures they are never used for gating.
load_dotenv(encoding="utf-8-sig")
os.environ.setdefault("PUBLIC_CHANNEL_ID", "0")
os.environ.setdefault("PUBLIC_CHANNEL_URL", "https://t.me")

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
from app.content.runner import main as content_main


# Preserve every production hardening layer first. The NEXUS customer hub is
# installed last so the new central Telegram-folder UX becomes the final
# customer-facing navigation surface without removing hardened services.
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

bot_main = main_module.main


async def _safe_content_runtime() -> None:
    """Content agents must never be allowed to take the Telegram bot offline."""
    try:
        await content_main()
    except asyncio.CancelledError:
        raise
    except Exception:
        main_module.log.exception(
            "[NEXUS] Agentic content runtime failed; Telegram bot remains online"
        )


async def main() -> None:
    bot_task = asyncio.create_task(bot_main(), name="nexus-telegram-bot")
    content_task = asyncio.create_task(_safe_content_runtime(), name="nexus-agentic-content")
    try:
        await asyncio.gather(bot_task, content_task)
    finally:
        for task in (bot_task, content_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(bot_task, content_task, return_exceptions=True)


_LOCK_HANDLE = None


def _acquire_single_instance_lock():
    """Allow only one NEXUS Telegram polling process per machine."""
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
