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


def test_invoice_payment_idempotency_helper_preserves_status_and_newest_order(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    uid = 990010
    other_uid = 990011
    db.upsert_user(uid, "payer", "Payer")
    db.upsert_user(other_uid, "other", "Other")

    old_id = db.create_payment(uid, "30", 30, "old", "irr", "old-file", "photo", invoice_id=7001)
    ignored_id = db.create_payment(uid, "30", 30, "ignored", "irr", "ignored-file", "photo", invoice_id=7001)
    newest_id = db.create_payment(uid, "30", 30, "newest", "irr", "new-file", "photo", invoice_id=7001)
    db.create_payment(other_uid, "30", 30, "other", "irr", "other-file", "photo", invoice_id=7001)

    with db.conn() as con:
        con.execute("UPDATE payments SET status='approved' WHERE id=?", (old_id,))
        con.execute("UPDATE payments SET status='failed' WHERE id=?", (ignored_id,))

    row = db.find_invoice_payment(uid, 7001)
    assert int(row["id"]) == newest_id
    assert str(row["status"]) == "pending"


def test_miniapp_execution_history_preserves_projection_newest_first_and_limit(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    uid = 990020
    db.upsert_user(uid, "history", "History")

    with db.conn() as con:
        for idx in range(3):
            con.execute(
                """INSERT INTO autotrade_trade_executions(
                       telegram_id,ticket,event_id,event_type,symbol,direction,volume,
                       entry_price,exit_price,profit,status,destination,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    uid, f"T{idx}", f"E{idx}", "OPEN", "XAUUSD", "BUY", 0.01,
                    4300 + idx, None, idx, "EXECUTED", "BOTH",
                    f"2026-10-07T00:00:0{idx}+00:00", f"2026-10-07T00:00:0{idx}+00:00",
                ),
            )

    rows = db.miniapp_execution_history(uid, limit=2)
    assert [str(r["ticket"]) for r in rows] == ["T2", "T1"]
    assert list(rows[0].keys()) == [
        "id", "ticket", "event_type", "symbol", "direction", "volume",
        "entry_price", "exit_price", "profit", "status", "created_at",
    ]


def test_admin_mt5_account_resolution_preserves_configured_fallback_and_latest_seen(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    db.record_mt5_heartbeat("A1", role="ADMIN", ea_version="0.6.5")
    db.record_mt5_heartbeat("A2", role="ADMIN", ea_version="0.6.5")
    db.record_mt5_heartbeat("CLIENT1", role="CLIENT", ea_version="0.6.5")
    with db.conn() as con:
        con.execute("UPDATE mt5_heartbeats_v060 SET last_seen_at='2026-10-07T10:00:00+00:00' WHERE account_number='A1'")
        con.execute("UPDATE mt5_heartbeats_v060 SET last_seen_at='2026-10-07T11:00:00+00:00' WHERE account_number='A2'")

    assert db.latest_admin_mt5_account(("A1", "A2")) == "A2"
    assert db.latest_admin_mt5_account(("MISSING",)) == "MISSING"
    assert db.latest_admin_mt5_account() == "A2"
    hb = db.admin_mt5_heartbeat("A2")
    assert str(hb["account_number"]) == "A2"
    assert str(hb["last_seen_at"]) == "2026-10-07T11:00:00+00:00"


def test_admin_mt5_live_state_helpers_preserve_case_managed_status_and_classification(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    db.upsert_mt5_live_snapshot(
        "ADMIN1",
        positions=[
            {
                "identifier": "P1", "ticket": "101", "signal_code": "nx-case",
                "symbol": "XAUUSD", "direction": "BUY", "volume": 0.01,
                "entry_price": 4300, "current_price": 4301, "stop_loss": 4290,
                "take_profit": 4320, "profit": 1.5, "magic": 1,
                "nexus_managed": True, "order_type": "MARKET",
            },
            {
                "identifier": "P2", "ticket": "102", "signal_code": "NX-UNMANAGED",
                "symbol": "XAUUSD", "direction": "BUY", "volume": 0.01,
                "entry_price": 4300, "current_price": 4301, "stop_loss": 4290,
                "take_profit": 4320, "profit": 0, "magic": 0,
                "nexus_managed": False, "order_type": "MARKET",
            },
        ],
        orders=[
            {
                "identifier": "O1", "ticket": "201", "signal_code": "NX-ORDER",
                "symbol": "XAUUSD", "direction": "SELL", "volume": 0.01,
                "entry_price": 4310, "current_price": 4305, "stop_loss": 4320,
                "take_profit": 4290, "magic": 1, "nexus_managed": True,
                "order_type": "LIMIT",
            }
        ],
    )

    live = db.mt5_latest_managed_signal_state("ADMIN1", "NX-CASE")
    assert live is not None
    assert str(live["ticket"]) == "101"

    rows = db.mt5_managed_active_state("ADMIN1")
    assert {str(r["ticket"]) for r in rows} == {"101", "201"}
    assert all(int(r["nexus_managed"]) == 1 for r in rows)


def test_phase2_migrated_callers_use_canonical_helpers_without_priority_sql():
    miniapp = (ROOT / "app/miniapp_api.py").read_text(encoding="utf-8")
    admin = (ROOT / "app/miniapp_admin_api.py").read_text(encoding="utf-8")

    assert "SELECT id,status FROM payments WHERE invoice_id=?" not in miniapp
    assert "FROM autotrade_trade_executions WHERE telegram_id=? ORDER BY id DESC LIMIT 20" not in miniapp
    assert "db.find_invoice_payment(uid, payload.invoice_id)" in miniapp
    assert "db.miniapp_execution_history(uid, limit=20)" in miniapp

    assert "SELECT account_number FROM mt5_heartbeats_v060" not in admin
    assert "SELECT account_number,ea_version,last_seen_at FROM mt5_heartbeats_v060" not in admin
    assert "SELECT * FROM mt5_live_state WHERE account_number=?" not in admin
    assert "db.latest_admin_mt5_account(configured)" in admin
    assert "db.admin_mt5_heartbeat(account)" in admin
    assert "db.mt5_latest_managed_signal_state(account, code)" in admin
    assert "db.mt5_managed_active_state(account)" in admin


def test_payment_delivery_state_is_idempotent_and_preserves_legacy_fields(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    uid = 990030
    db.upsert_user(uid, "delivery", "Delivery")
    payment_id = db.create_payment(uid, "30", 30, "test", "irr", "placeholder", "photo")

    db.set_payment_delivery_state(
        payment_id,
        delivered=True,
        receipt_file_id="tg-file-1",
        receipt_message_id=501,
    )
    db.set_payment_delivery_state(
        payment_id,
        delivered=True,
        receipt_file_id="tg-file-1",
        receipt_message_id=501,
    )
    row = db.get_payment(payment_id)
    assert str(row["status"]) == "pending"
    assert str(row["receipt_file_id"]) == "tg-file-1"
    assert int(row["receipt_message_id"]) == 501

    failed_id = db.create_payment(uid, "30", 30, "failed", "irr", "placeholder-2", "photo")
    note = "Mini App admin delivery failed: TelegramError"
    db.set_payment_delivery_state(failed_id, delivered=False, error_text=note)
    db.set_payment_delivery_state(failed_id, delivered=False, error_text=note)
    failed = db.get_payment(failed_id)
    assert str(failed["status"]) == "failed"
    assert str(failed["admin_note"]) == note


def test_atomic_live_repair_deduplicates_business_identity_across_transport_event_ids(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    uid = 990040
    db.upsert_user(uid, "repair", "Repair")
    signal = db.create_signal(
        market_type="FOREX", symbol="EURUSD", direction="BUY",
        entry_price=1.10, stop_loss=1.09, targets=[1.11],
        risk_percent=1.0, rr_ratio=1.0, destination="BOTH",
        chart_file_id=None, created_by=uid,
    )
    sid = int(signal["id"])
    base = {
        "event": "OPEN", "ticket": "T-REPAIR", "signal_id": str(signal["code"]),
        "symbol": "EURUSD", "direction": "BUY", "volume": 0.01,
        "entry_price": 1.10, "stop_loss": 1.09, "take_profit": 1.11,
        "destination": "BOTH", "position_id": "POS-1",
    }

    first = db.reconcile_live_trade_execution(
        uid, sid, "T-REPAIR", "OPEN", {**base, "event_id": "LIVE-OPEN-POS-1"},
        destination="BOTH",
    )
    second = db.reconcile_live_trade_execution(
        uid, sid, "T-REPAIR", "OPEN", {**base, "event_id": "MT5-ORIGINAL-999"},
        destination="BOTH",
    )

    assert first["created"] is True
    assert second["created"] is False
    assert int(first["id"]) == int(second["id"])

    with db.conn() as con:
        rows = con.execute(
            "SELECT * FROM autotrade_trade_executions "
            "WHERE telegram_id=? AND ticket=? AND signal_id=? AND event_type='OPEN'",
            (uid, "T-REPAIR", sid),
        ).fetchall()
        notifications = con.execute(
            "SELECT * FROM autotrade_notifications WHERE telegram_id=? AND event_type='MT5_TRADE_EVENT'",
            (uid,),
        ).fetchall()

    assert len(rows) == 1
    assert str(rows[0]["status"]) == "RECONCILED"
    assert str(rows[0]["event_id"]) == "LIVE-OPEN-POS-1"
    assert len(notifications) == 1


def test_atomic_live_repair_reuses_same_transport_event_without_duplicate(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    uid = 990041
    db.upsert_user(uid, "repair2", "Repair2")
    signal = db.create_signal(
        market_type="FOREX", symbol="GBPUSD", direction="BUY",
        entry_price=1.25, stop_loss=1.24, targets=[1.26],
        risk_percent=1.0, rr_ratio=1.0, destination="BOTH",
        chart_file_id=None, created_by=uid,
    )
    sid = int(signal["id"])
    payload = {
        "event": "PENDING", "ticket": "T-PEND", "signal_id": str(signal["code"]),
        "symbol": "GBPUSD", "direction": "BUY", "volume": 0.02,
        "entry_price": 1.25, "stop_loss": 1.24, "take_profit": 1.26,
        "event_id": "LIVE-PENDING-ORDER-1", "destination": "BOTH",
        "position_id": "ORDER-1",
    }

    a = db.reconcile_live_trade_execution(uid, sid, "T-PEND", "PENDING", payload)
    b = db.reconcile_live_trade_execution(uid, sid, "T-PEND", "PENDING", payload)

    assert a["created"] is True
    assert b["created"] is False
    with db.conn() as con:
        count = con.execute(
            "SELECT COUNT(*) FROM autotrade_trade_executions "
            "WHERE telegram_id=? AND ticket=? AND signal_id=? AND event_type='PENDING'",
            (uid, "T-PEND", sid),
        ).fetchone()[0]
    assert count == 1


def test_phase3_callers_no_longer_embed_payment_delivery_or_live_repair_sql():
    miniapp = (ROOT / "app/miniapp_api.py").read_text(encoding="utf-8")
    autotrade = (ROOT / "app/autotrade/api.py").read_text(encoding="utf-8")

    assert "UPDATE payments SET receipt_file_id=?,receipt_message_id=? WHERE id=?" not in miniapp
    assert "UPDATE payments SET status='failed',admin_note=? WHERE id=?" not in miniapp
    assert "db.set_payment_delivery_state(" in miniapp

    assert "WHERE telegram_id=? AND ticket=? AND signal_id=? AND event_type=?" not in autotrade
    assert "db.reconcile_live_trade_execution(" in autotrade


def test_atomic_live_repair_serializes_concurrent_different_event_ids(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    db = _fresh_db(monkeypatch, tmp_path)
    uid = 990042
    db.upsert_user(uid, "concurrent", "Concurrent")
    signal = db.create_signal(
        market_type="FOREX", symbol="USDJPY", direction="BUY",
        entry_price=150.0, stop_loss=149.0, targets=[151.0],
        risk_percent=1.0, rr_ratio=1.0, destination="BOTH",
        chart_file_id=None, created_by=uid,
    )
    sid = int(signal["id"])
    base = {
        "event": "OPEN", "ticket": "T-RACE", "signal_id": str(signal["code"]),
        "symbol": "USDJPY", "direction": "BUY", "volume": 0.01,
        "entry_price": 150.0, "stop_loss": 149.0, "take_profit": 151.0,
        "destination": "BOTH", "position_id": "POS-RACE",
    }

    def run(event_id):
        return db.reconcile_live_trade_execution(
            uid, sid, "T-RACE", "OPEN", {**base, "event_id": event_id},
            destination="BOTH",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ["LIVE-RACE-A", "LIVE-RACE-B"]))

    with db.conn() as con:
        rows = con.execute(
            "SELECT * FROM autotrade_trade_executions "
            "WHERE telegram_id=? AND ticket=? AND signal_id=? AND event_type='OPEN'",
            (uid, "T-RACE", sid),
        ).fetchall()

    assert len(rows) == 1
    assert sorted(bool(r["created"]) for r in results) == [False, True]
    assert str(rows[0]["status"]) == "RECONCILED"
