from datetime import datetime, timezone
import sqlite3


def _fresh_db(monkeypatch, tmp_path):
    from app import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    return db


def test_reconcile_close_repairs_signal_and_is_idempotent(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    uid = 1001
    now = datetime.now(timezone.utc).isoformat()
    with db.conn() as con:
        con.execute("INSERT INTO users(telegram_id,created_at,updated_at) VALUES(?,?,?)", (uid, now, now))

    sig = db.create_signal(
        market_type="CRYPTO", symbol="BTCUSDT", direction="LONG", entry_price=100,
        stop_loss=95, targets=[110], risk_percent=1, rr_ratio=2,
        destination="VIP", chart_file_id=None, created_by=uid, publish_token="SIG-1",
    )
    with db.conn() as con:
        con.execute("UPDATE signals SET status='ACTIVE' WHERE id=?", (sig["id"],))

    item = {
        "event": "CLOSE", "ticket": "9001", "event_id": "RECON-CLOSE-77-9001",
        "signal_id": "SIG-1", "symbol": "BTCUSDT", "direction": "LONG",
        "volume": 0.01, "entry_price": 100, "stop_loss": 95, "take_profit": 110,
        "exit_price": 108, "profit": 8.5, "event_time_ms": 1750000000000,
        "destination": "VIP",
    }
    result = db.reconcile_mt5_history(uid, [item])
    assert result["created"] == 1
    assert result["repaired"] == 1

    row = db.get_signal(sig["id"])
    assert row["status"] == "CLOSED"
    assert row["exit_price"] == 108
    assert row["result_value"] == 8.5
    assert row["result_unit"] == "USD"

    again = db.reconcile_mt5_history(uid, [item])
    assert again["created"] == 0
    assert db.autotrade_trade_executions(uid, limit=50)


def test_reconcile_open_links_signal_without_closing(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    uid = 1002
    now = datetime.now(timezone.utc).isoformat()
    with db.conn() as con:
        con.execute("INSERT INTO users(telegram_id,created_at,updated_at) VALUES(?,?,?)", (uid, now, now))

    sig = db.create_signal(
        market_type="FOREX", symbol="EURUSD", direction="LONG", entry_price=1.1,
        stop_loss=1.09, targets=[1.12], risk_percent=1, rr_ratio=2,
        destination="FREE", chart_file_id=None, created_by=uid, publish_token="SIG-OPEN",
    )
    with db.conn() as con:
        con.execute("UPDATE signals SET status='ACTIVE' WHERE id=?", (sig["id"],))

    item = {
        "event": "OPEN", "ticket": "7001", "event_id": "RECON-OPEN-77-7001",
        "signal_id": "SIG-OPEN", "symbol": "EURUSD", "direction": "LONG",
        "volume": 0.1, "entry_price": 1.1002, "stop_loss": 1.09, "take_profit": 1.12,
        "event_time_ms": 1750000000000, "destination": "FREE",
    }
    result = db.reconcile_mt5_history(uid, [item])
    assert result["matched"] == 1
    row = db.get_signal(sig["id"])
    assert row["status"] == "ACTIVE"
    ex = db.autotrade_trade_executions(uid, limit=50)
    assert len(ex) == 1
    assert ex[0]["event_type"] == "OPEN"
    assert ex[0]["signal_id"] == sig["id"]


def test_reconciliation_schema_contains_execution_truth_fields():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    api=(root/"app/autotrade/api.py").read_text(encoding="utf-8")
    ea=(root/"mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
    assert "gross_profit" in api and "commission" in api and "swap" in api
    assert "position_id" in api and "deal_id" in api and "cycle_id" in api
    assert "PositionInitialRiskCash" in ea
