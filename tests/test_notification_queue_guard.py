from datetime import datetime, timezone, timedelta


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


def _fresh_event_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _install_live_open(db, uid: int, sig, *, seen_at: str | None = None):
    now = seen_at or datetime.now(timezone.utc).isoformat()
    account = "80150619"
    with db.conn() as con:
        con.execute(
            "INSERT INTO autotrade_mt5_accounts(telegram_id,account_number,status,bound_at,last_seen_at) "
            "VALUES(?,?,?,?,?)",
            (uid, account, "active", now, now),
        )
        con.execute(
            """
            INSERT INTO mt5_live_state(
                account_number,state_type,identifier,ticket,signal_code,symbol,direction,
                volume,entry_price,current_price,stop_loss,take_profit,profit,magic,
                nexus_managed,order_type,status,broker,server,last_seen_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                account, "POSITION", "95296019", "95296019", str(sig["code"]),
                "XAUUSD.EC", "SHORT", 0.01, 4384.10, 4360.0, 4372.21, 4318.0,
                37.55, 258025, 1, "MARKET", "OPEN", "TestBroker", "TestServer", now,
            ),
        )
    return account


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
        "event_time_ms": _fresh_event_ms(),
    }
    reason = guard._identity_rejection_reason(uid, payload, signal_db_id=int(sig["id"]))
    assert reason and "direction mismatch" in reason


def test_reconcile_short_alias_matches_sell_signal(monkeypatch, tmp_path):
    db, uid, sig = _fresh_signal(monkeypatch, tmp_path, direction="SELL")
    from app.autotrade import notification_queue_guard as guard
    payload = {
        "event": "OPEN", "event_id": "RECON-OPEN-95296019-78377594",
        "signal_id": sig["code"], "ticket": "95296019",
        "symbol": "XAUUSD.EC", "direction": "SHORT",
        "entry_price": 4384.10,
        "event_time_ms": _fresh_event_ms(),
    }
    assert guard._identity_rejection_reason(uid, payload, signal_db_id=int(sig["id"])) is None


def test_reconcile_long_alias_matches_buy_signal(monkeypatch, tmp_path):
    db, uid, sig = _fresh_signal(monkeypatch, tmp_path, direction="BUY")
    from app.autotrade import notification_queue_guard as guard
    payload = {
        "event": "OPEN", "event_id": "RECON-OPEN-100-101",
        "signal_id": sig["code"], "ticket": "100",
        "symbol": "XAUUSD.EC", "direction": "LONG",
        "entry_price": 4384.10,
        "event_time_ms": _fresh_event_ms(),
    }
    assert guard._identity_rejection_reason(uid, payload, signal_db_id=int(sig["id"])) is None


def test_reconcile_close_is_suppressed_while_fresh_live_position_is_open(monkeypatch, tmp_path):
    db, uid, sig = _fresh_signal(monkeypatch, tmp_path, direction="SELL")
    _install_live_open(db, uid, sig)
    from app.autotrade import notification_queue_guard as guard

    payload = {
        "event": "CLOSE",
        "event_id": "RECON-CLOSE-95296019-78379999",
        "signal_id": sig["code"],
        "ticket": "78379999",
        "position_id": "95296019",
        "symbol": "XAUUSD.EC",
        "direction": "SHORT",
        "entry_price": 4384.10,
        "event_time_ms": _fresh_event_ms(),
    }

    reason = guard._identity_rejection_reason(uid, payload, signal_db_id=int(sig["id"]))
    assert reason
    assert "live position is still OPEN" in reason


def test_stale_live_open_does_not_block_legitimate_reconcile_close(monkeypatch, tmp_path):
    db, uid, sig = _fresh_signal(monkeypatch, tmp_path, direction="SELL")
    stale = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    _install_live_open(db, uid, sig, seen_at=stale)
    from app.autotrade import notification_queue_guard as guard

    payload = {
        "event": "CLOSE",
        "event_id": "RECON-CLOSE-95296019-78380000",
        "signal_id": sig["code"],
        "ticket": "78380000",
        "position_id": "95296019",
        "symbol": "XAUUSD.EC",
        "direction": "SHORT",
        "entry_price": 4384.10,
        "event_time_ms": _fresh_event_ms(),
    }

    assert guard._identity_rejection_reason(uid, payload, signal_db_id=int(sig["id"])) is None
