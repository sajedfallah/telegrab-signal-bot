from datetime import datetime, timezone


def _fresh_signal(monkeypatch, tmp_path, *, direction="SHORT"):
    from app import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "queue_guard.db")
    db.init_db()
    uid = 400112107
    now = datetime.now(timezone.utc).isoformat()
    with db.conn() as con:
        con.execute("INSERT INTO users(telegram_id,created_at,updated_at) VALUES(?,?,?)", (uid, now, now))
    sig = db.create_signal(
        market_type="GOLD", symbol="XAUUSD", direction=direction,
        entry_price=4384.10, stop_loss=4393.0, targets=[4370.0],
        risk_percent=1.0, rr_ratio=None, destination="BOTH",
        chart_file_id=None, created_by=uid, publish_token="PUB-4",
    )
    return db, uid, sig


def test_corrupt_reconcile_timestamp_is_rejected(monkeypatch, tmp_path):
    db, uid, sig = _fresh_signal(monkeypatch, tmp_path)
    from app.autotrade import notification_queue_guard as guard
    payload = {
        "event": "CLOSE", "event_id": "RECON-CLOSE-92478690-75725592",
        "signal_id": sig["code"], "ticket": "75725592",
        "symbol": "XAUUSD.EC", "direction": "LONG",
        "entry_price": 4311.0, "event_time_ms": 75725592,
    }
    reason = guard._identity_rejection_reason(uid, payload, signal_db_id=int(sig["id"]))
    assert reason and "event_time_ms" in reason


def test_direct_close_is_never_filtered(monkeypatch, tmp_path):
    db, uid, sig = _fresh_signal(monkeypatch, tmp_path)
    from app.autotrade import notification_queue_guard as guard
    payload = {
        "event": "CLOSE", "event_id": "CLOSE-92795808-75990511",
        "signal_id": sig["code"], "ticket": "75990511",
        "symbol": "XAUUSD.EC", "direction": "SHORT",
        "entry_price": 4384.10, "event_time_ms": 1788402052000,
    }
    assert guard._identity_rejection_reason(uid, payload, signal_db_id=int(sig["id"])) is None


def test_valid_epoch_still_rejects_recycled_direction(monkeypatch, tmp_path):
    db, uid, sig = _fresh_signal(monkeypatch, tmp_path)
    from app.autotrade import notification_queue_guard as guard
    payload = {
        "event": "CLOSE", "event_id": "RECON-CLOSE-999-888",
        "signal_id": sig["code"], "ticket": "888",
        "symbol": "XAUUSD.EC", "direction": "LONG",
        "entry_price": 4384.10,
        "event_time_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
    }
    reason = guard._identity_rejection_reason(uid, payload, signal_db_id=int(sig["id"]))
    assert reason and "direction mismatch" in reason
