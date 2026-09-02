from __future__ import annotations


def _fresh_db(monkeypatch, tmp_path):
    from app import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    from app.autotrade.lifecycle_identity_guard import install_lifecycle_identity_guard
    install_lifecycle_identity_guard()
    return db


def _issue_short_admin_signal(db, uid: int, account: str):
    return db.issue_mt5_admin_signal(
        market_type="GOLD",
        symbol="XAUUSD",
        direction="SHORT",
        entry_price=4387.0,
        stop_loss=4393.0,
        targets=[4382.0, 4378.0],
        risk_percent=1.0,
        rr_ratio=None,
        order_type="MARKET",
        volume_mode="RISK",
        admin_account=account,
        admin_id=uid,
        request_id="ADMIN-ISSUE-1",
        destination="BOTH",
    )


def test_lifecycle_lookup_accepts_canonical_nx_code(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    uid = 1001
    account = "80150619"
    row = _issue_short_admin_signal(db, uid, account)

    # MT5 sends the canonical NX-* code from the broker position/deal comment,
    # while the original backend resolver only compared against publish_token.
    assert str(row["code"]).startswith("NX-")
    assert str(row["publish_token"]) != str(row["code"])

    resolved = db.get_signal_by_autotrade_signal_id(uid, str(row["code"]))
    assert resolved is not None
    assert int(resolved["id"]) == int(row["id"])


def test_lifecycle_lookup_keeps_admin_owner_boundary(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    row = _issue_short_admin_signal(db, 1001, "80150619")

    assert db.get_signal_by_autotrade_signal_id(9999, str(row["code"])) is None


def test_broker_open_reuses_existing_market_signal_before_tp_validation(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    uid = 1001
    account = "80150619"
    original = _issue_short_admin_signal(db, uid, account)

    # A broker OPEN for an already-issued signal may report TP=0 during the
    # transaction/live-state timing window. Legacy code attempted to create a
    # second SHORT signal with target==entry and failed forever with:
    # "SHORT take-profit targets must be below entry".
    reused = db.issue_mt5_admin_signal(
        market_type="GOLD",
        symbol="XAUUSD.EC",
        direction="SHORT",
        entry_price=4387.0,
        stop_loss=4393.0,
        targets=[4387.0],  # deliberately invalid if a new signal were created
        risk_percent=0.0,
        rr_ratio=None,
        order_type="MARKET",
        volume_mode="FIXED",
        lot_size=0.01,
        trailing_name="Manual MT5",
        admin_account=account,
        admin_id=uid,
        request_id="OPEN-92793444-75987815",
        signal_code=str(original["code"]),
        destination="BOTH",
    )

    assert int(reused["id"]) == int(original["id"])
    with db.conn() as con:
        count = int(con.execute("SELECT COUNT(*) FROM signals").fetchone()[0])
    assert count == 1


def test_non_lifecycle_issue_still_validates_bad_short_target(monkeypatch, tmp_path):
    import pytest

    db = _fresh_db(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="SHORT take-profit targets must be below entry"):
        db.issue_mt5_admin_signal(
            market_type="GOLD",
            symbol="XAUUSD",
            direction="SHORT",
            entry_price=4387.0,
            stop_loss=4393.0,
            targets=[4387.0],
            risk_percent=1.0,
            rr_ratio=None,
            order_type="MARKET",
            admin_account="80150619",
            admin_id=1001,
            request_id="ADMIN-NEW-SIGNAL",
            destination="BOTH",
        )
