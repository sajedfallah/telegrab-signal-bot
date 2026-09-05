from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT = (ROOT / "app/main.py").read_text(encoding="utf-8")
UI = (ROOT / "app/ui.py").read_text(encoding="utf-8")
WEB = (ROOT / "app/admin_api.py").read_text(encoding="utf-8")
DB = (ROOT / "app/db.py").read_text(encoding="utf-8")


def test_critical_telegram_admin_capabilities_remain_discoverable():
    callbacks = {
        "admin_users", "admin_pending", "admin_plans", "admin_discounts",
        "admin_rewards", "admin_campaigns", "admin_broadcast", "admin_audit",
        "admin_backup", "admin_channels_status", "admin_signals",
        "admin_mt5_account_changes", "pricing_settings",
    }
    for callback in callbacks:
        assert f'F.data == "{callback}"' in BOT or f'"{callback}"' in UI


def test_trade_mutations_share_the_central_ea_command_queue():
    for command in (
        "CLOSE_SIGNAL", "MOVE_SL_TO_ENTRY",
        "PARTIAL_CLOSE", "UPDATE_SL", "UPDATE_TP", "ACTIVATE_TRAILING",
    ):
        assert command in DB
        assert command in WEB
    assert "db.add_signal_update" in BOT
    assert "command_map" in DB
    assert "create_autotrade_command" in WEB
    # Pending cancellation is available to Web/MT5 but Telegram still needs a
    # dedicated button/flow; keep this asymmetry explicit rather than masking it.
    assert "CANCEL_PENDING" in WEB


def test_web_mutations_have_role_checks_and_audit_primitive():
    assert 'Depends(require("ADMIN", "MODERATOR"))' in WEB
    assert 'Depends(require("ADMIN"))' in WEB
    assert "def _audit(" in WEB
