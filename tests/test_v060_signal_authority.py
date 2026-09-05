from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
API = (ROOT / "app" / "autotrade" / "api.py").read_text(encoding="utf-8")
EA = (ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")


def test_v060_mt5_is_canonical_signal_authority():
    assert "issuer_type='MT5_ADMIN'" in MAIN or "issuer_type='MT5_ADMIN'" in (ROOT / "app" / "db.py").read_text(encoding="utf-8")
    assert "/api/v1/admin/mt5/signals" in API
    assert "authorize_admin_mt5" in API


def test_v060_client_distribution_does_not_require_telegram_message_ids():
    db = (ROOT / "app" / "db.py").read_text(encoding="utf-8")
    assert "issuer_type='MT5_ADMIN'" in db
    assert "signal_deliveries_v060" in db


def test_v060_telegram_signal_handlers_are_not_registered():
    assert "_disable_telegram_signal_authority" in MAIN
    assert '"signal_create"' in MAIN
    assert '"signal_publish"' in MAIN


def test_v060_audit_and_heartbeat_tables_exist_in_source():
    db = (ROOT / "app" / "db.py").read_text(encoding="utf-8")
    assert "signal_events_v060" in db
    assert "mt5_heartbeats_v060" in db
    assert "add_signal_event" in db
    assert "record_mt5_heartbeat" in db


def test_v060_ea_declares_new_authority():
    assert 'NEXUS_EA_VERSION "0.6.5"' in EA
    assert "MT5 ADMIN ONLY" in EA
    assert "TELEGRAM     REPORTING ONLY" in EA


def test_v060_no_telegram_publish_in_mt5_event_worker():
    block = MAIN[MAIN.index("async def _process_mt5_trade_event"):MAIN.index("async def autotrade_notification_worker")]
    assert "await _reply_signal_update" not in block
    assert "_publish_one_channel" not in block


def test_v060_telegram_admin_signal_center_is_reporting_only():
    ui = (ROOT / "app" / "ui.py").read_text(encoding="utf-8")
    main = MAIN
    assert '"signal_create"' not in ui[ui.index('def signal_center_menu'):ui.index('def signal_market_menu')]
    assert '"signal_active"' in ui[ui.index('def signal_center_menu'):ui.index('def signal_market_menu')]
    assert '"signal_closed"' in ui[ui.index('def signal_center_menu'):ui.index('def signal_market_menu')]
    assert '"signal_stats"' in ui[ui.index('def signal_center_menu'):ui.index('def signal_market_menu')]
    blocked = main[main.index('blocked_callback = {'):main.index('router.callback_query.handlers', main.index('blocked_callback = {'))]
    assert '"admin_signals"' not in blocked
    assert '"signal_create"' in blocked
    assert '"signal_publish"' in blocked


def test_v060_mt5_minimize_removes_all_signal_form_objects():
    assert 'DeleteAdminSignalPanel();' in EA[EA.index('if(g_panel_minimized)'):EA.index('if(g_panel_minimized)')+500]
    assert 'g_admin_signal_symbol' in EA[EA.index('void PaintAdminSignalPanel()'):EA.index('string AdminSignalMarketType')]


def test_v060_signal_id_is_server_generated_for_mt5_authority():
    db = (ROOT / "app" / "db.py").read_text(encoding="utf-8")
    api = (ROOT / "app" / "autotrade" / "api.py").read_text(encoding="utf-8")
    assert 'code = f"NX-{signal_id:02d}"' in db
    assert 'token = str(signal_code or "").strip() or ("MT5ADMIN-" + secrets.token_urlsafe(18))' in db
    assert 'signal_code=req.signal_code' in api
