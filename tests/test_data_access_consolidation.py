from __future__ import annotations

import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _fresh_db(monkeypatch, tmp_path):
    import app.db as db
    db = importlib.reload(db)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "nexus_bot.db")
    db.init_db()
    return db


def test_miniapp_autotrade_reuses_canonical_account_access(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    uid = 990001
    db.upsert_user(uid, "data_access", "Data Access")
    db.bind_mt5_account(uid, "123456", "Broker", "Server", "0.6.5")
    db.set_exchange_account_placeholder(uid, "binance")

    import app.miniapp_api as api
    monkeypatch.setattr(api.db, "DB_PATH", db.DB_PATH)

    out = api._autotrade(uid)
    assert out["mt5"]["account_number"] == "123456"
    assert out["mt5"]["broker"] == "Broker"
    assert out["exchange"]["exchange"] == "binance"


def test_admin_receipt_repository_helper_preserves_upsert(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    uid = 990002
    db.upsert_user(uid, "receipt", "Receipt")
    payment_id = db.create_payment(uid, "30", 30, "test", "irr", "file", "photo")

    db.save_admin_receipt(payment_id, 1, 100)
    db.save_admin_receipt(payment_id, 1, 101)

    rows = db.list_admin_receipts(payment_id)
    assert len(rows) == 1
    assert int(rows[0]["message_id"]) == 101


def test_mt5_admin_signal_listing_preserves_descending_limit(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    admin_id = 990003
    db.upsert_user(admin_id, "admin", "Admin")

    first = db.issue_mt5_admin_signal(
        market_type="GOLD", symbol="XAUUSD", direction="BUY",
        entry_price=4300, stop_loss=4290, targets=[4310],
        risk_percent=1, rr_ratio=None, order_type="MARKET",
        volume_mode="FIXED", lot_size=0.01, destination="BOTH",
        admin_account="10001", admin_id=admin_id, request_id="DAC-1",
        signal_code=None, timeframe="M5",
    )
    second = db.issue_mt5_admin_signal(
        market_type="GOLD", symbol="XAUUSD", direction="SELL",
        entry_price=4320, stop_loss=4330, targets=[4310],
        risk_percent=1, rr_ratio=None, order_type="MARKET",
        volume_mode="FIXED", lot_size=0.01, destination="BOTH",
        admin_account="10001", admin_id=admin_id, request_id="DAC-2",
        signal_code=None, timeframe="M5",
    )

    rows = db.list_mt5_admin_signals(1)
    assert [int(r["id"]) for r in rows] == [int(second["id"])]
    assert int(second["id"]) > int(first["id"])


def test_migrated_callers_no_longer_embed_duplicate_sql():
    miniapp = (ROOT / "app/miniapp_api.py").read_text(encoding="utf-8")
    admin = (ROOT / "app/miniapp_admin_api.py").read_text(encoding="utf-8")

    assert "FROM autotrade_mt5_accounts WHERE telegram_id=?" not in miniapp
    assert "FROM autotrade_exchange_accounts WHERE telegram_id=?" not in miniapp
    assert "INSERT OR REPLACE INTO admin_receipts" not in miniapp
    assert "db.mt5_account(uid)" in miniapp
    assert "db.exchange_account(uid)" in miniapp
    assert "db.save_admin_receipt(" in miniapp

    assert "SELECT * FROM signals WHERE issuer_type='MT5_ADMIN' ORDER BY id DESC LIMIT 100" not in admin
    assert "db.list_mt5_admin_signals(100)" in admin
