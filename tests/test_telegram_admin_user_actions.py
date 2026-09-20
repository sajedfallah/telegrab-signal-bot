from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
UI = (ROOT / "app" / "ui.py").read_text(encoding="utf-8")
STATES = (ROOT / "app" / "states.py").read_text(encoding="utf-8")


def test_telegram_signal_authority_is_registered_at_runtime():
    assert "_disable_telegram_signal_authority()" not in MAIN
    for route in (
        'F.data == "signal_create"',
        'F.data.startswith("sigmarket:")',
        'F.data.startswith("sigsymbol:")',
        'F.data.startswith("sigdir:")',
        'F.data.startswith("sigtf:")',
        'F.data.startswith("sigorder:")',
        'F.data.startswith("sigvol:")',
        'F.data.startswith("sigtrail:")',
        'F.data.startswith("sigdest:")',
        'F.data == "sigpublish"',
        'F.data.startswith("sigmanage:")',
        'F.data.startswith("sigact:")',
    ):
        assert route in MAIN


def test_admin_signal_ui_exposes_creation_and_lifecycle_actions():
    assert '"signal_create"' in UI
    assert '"signal_analytics"' not in UI
    assert '"admin_dashboard"' in UI
    for action in ("limitactive", "be", "partial", "tp", "sl", "trailing", "close"):
        assert f"sigact:{action}:" in UI


def test_plan_access_and_renewal_are_connected_to_backend():
    for route in (
        'F.data.startswith("planaccess:")',
        'F.data.startswith("planent:")',
        'F.data.startswith("planrenew:")',
    ):
        assert route in MAIN
    assert "db.update_plan_entitlement" in MAIN
    assert "db.update_plan_renewal_discount" in MAIN
    assert "admin_plan_renewal = State()" in STATES
    assert "admin_plan_access_menu" in UI


def test_primary_user_actions_have_callbacks():
    for route in (
        'F.data == "client_signals"',
        'F.data == "client_vip_access"',
        'F.data == "client_autotrade_access"',
        'F.data == "autotrade_status"',
        'F.data == "autotrade_open"',
        'F.data == "autotrade_history"',
        'F.data == "autotrade_today"',
        'F.data == "autotrade_license"',
        'F.data == "autotrade_download_mt5"',
        'F.data == "autotrade_account_change"',
        'F.data == "autotrade_exchange"',
        'F.data == "account"',
        'F.data == "my_payments"',
        'F.data == "referral"',
        'F.data == "vip"',
        'F.data == "support"',
    ):
        assert route in MAIN


def test_primary_admin_actions_have_callbacks():
    for route in (
        'F.data == "admin_users"',
        'F.data == "admin_subs"',
        'F.data == "admin_pending"',
        'F.data == "admin_plans"',
        'F.data == "admin_discounts"',
        'F.data == "admin_rewards"',
        'F.data == "admin_campaigns"',
        'F.data == "admin_broadcast"',
        'F.data == "admin_autotrade"',
        'F.data == "admin_dashboard"',
        'F.data == "admin_audit"',
        'F.data == "admin_backup"',
        'F.data == "admin_signals"',
    ):
        assert route in MAIN


def test_pending_signal_activation_supports_all_pending_order_types():
    assert '{"LIMIT","BUY_LIMIT","SELL_LIMIT","BUY_STOP","SELL_STOP","BUY_STOP_LIMIT","SELL_STOP_LIMIT"}' in MAIN


def test_telegram_active_signals_are_visible_in_admin_center():
    assert "db.list_active_signals(50)" in MAIN
    assert "Active Telegram Admin Signals" in MAIN
