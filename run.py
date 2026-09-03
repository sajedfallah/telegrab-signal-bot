import asyncio
import os
from pathlib import Path

import app.main as main_module
from app.main import main
from app.autotrade.event_time_guard import install_mt5_event_datetime_helper
from app.autotrade.result_card_guard import install_result_card_formatter
from app.ux_runtime_patch import install as install_user_ux_hardening
from app.services.pricing_admin_runtime import install as install_pricing_admin_runtime
from app.services.account_runtime import install as install_account_runtime
from app.services.market_brief_service import install as install_market_brief_runtime


# app.main must be fully imported before runtime lifecycle helpers are injected
# into its module globals. Calling these here is deterministic and idempotent.
install_mt5_event_datetime_helper()
install_result_card_formatter()
install_user_ux_hardening(main_module)
install_pricing_admin_runtime(main_module)
install_account_runtime(main_module)
install_market_brief_runtime(main_module)


_LOCK_HANDLE = None


def _acquire_single_instance_lock():
    """Allow only one NEXUS Telegram polling process per machine.

    Telegram permits only one long-polling getUpdates consumer per bot token.
    Using the OS temp directory makes the lock common to old/new project
    checkouts instead of tying it to a particular repository folder.
    """
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
