from datetime import datetime, timedelta, timezone
import importlib
from pathlib import Path

import pytest
from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]


def _fresh_db(monkeypatch, tmp_path):
    import app.db as db
    db = importlib.reload(db)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "nexus_bot.db")
    db.init_db()
    db.upsert_user(400112107, "admin", "Admin")
    return db


def _admin_signal(db, *, order_type="MARKET"):
    return db.issue_mt5_admin_signal(
        market_type="GOLD", symbol="XAUUSD", direction="BUY",
        entry_price=4310, stop_loss=4307, targets=[4315], risk_percent=1,
        rr_ratio=None, order_type=order_type, volume_mode="FIXED", lot_size=0.01,
        destination="BOTH", admin_account="80150619", admin_id=400112107,
        request_id=f"V065-{order_type}", timeframe="M5",
    )


def _auth(monkeypatch, api):
    monkeypatch.setattr(api, "_admin_auth", lambda *a, **k: {"telegram_id": 400112107, "mode": "ADMIN"})
    monkeypatch.setattr(api, "_resolve_ea_auth", lambda *a, **k: {"telegram_id": 400112107})


def test_enum_patterns_reject_partial_matches():
    from app.autotrade.api import SignalReceiptRequest, MT5AdminSignalRequest
    with pytest.raises(ValidationError):
        SignalReceiptRequest(license_key="x", account_number="123", signal_db_id=1, status="executed_EVIL")
    with pytest.raises(ValidationError):
        MT5AdminSignalRequest(symbol="X", direction="BUY_EVIL", entry_price=2, stop_loss=1, targets=[3])


def test_unicode_admin_token_is_cleanly_rejected(monkeypatch):
    from app.autotrade.service import AutoTradeError, authorize_admin_mt5
    with pytest.raises(AutoTradeError, match="admin authorization rejected"):
        authorize_admin_mt5("80150619", "کلید نامعتبر")


def test_close_signal_uses_persisted_ticket_when_comment_is_cleared():
    source = (ROOT / "mt5" / "NEXUS_AutoTrade" / "Include" / "TradeManager.mqh").read_text(encoding="utf-8")
    close = source[source.index("bool CloseSignal"):source.index("bool ModifySL")]
    assert "ulong saved=SavedTicket(signal_id);" in close
    assert "ticket!=saved" in close


def test_executed_receipt_requires_current_matching_position(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    signal = _admin_signal(db)
    from app.autotrade import api
    _auth(monkeypatch, api)
    with pytest.raises(HTTPException) as exc:
        api.signal_receipt_mt5_get(BackgroundTasks(), int(signal["id"]), "executed", "T1", None, "", "80150619", "true", "token")
    assert exc.value.status_code == 409

    db.upsert_mt5_live_snapshot("80150619", positions=[{
        "identifier":"P1", "ticket":"T1", "signal_code":signal["code"],
        "symbol":"XAUUSD.ec", "direction":"LONG", "volume":0.01,
        "entry_price":4310, "current_price":4311, "stop_loss":4307,
        "take_profit":4315, "profit":1, "magic":258025,
        "nexus_managed":True, "order_type":"MARKET",
    }])
    out = api.signal_receipt_mt5_get(BackgroundTasks(), int(signal["id"]), "executed", "T1", None, "", "80150619", "true", "token")
    assert out["publication"] == "QUEUED"


def test_pending_receipt_requires_current_matching_order(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    signal = _admin_signal(db, order_type="BUY_LIMIT")
    from app.autotrade import api
    _auth(monkeypatch, api)
    db.upsert_mt5_live_snapshot("80150619", orders=[{
        "identifier":"O1", "ticket":"O1", "signal_code":signal["code"],
        "symbol":"XAUUSD.ec", "direction":"LONG", "volume":0.01,
        "entry_price":4310, "current_price":4311, "stop_loss":4307,
        "take_profit":4315, "profit":0, "magic":258025,
        "nexus_managed":True, "order_type":"BUY_LIMIT",
    }])
    out = api.signal_receipt_mt5_get(BackgroundTasks(), int(signal["id"]), "pending", "O1", None, "", "80150619", "true", "token")
    assert out["publication"] == "QUEUED"


def test_receipt_accepts_exact_nexus_ticket_when_broker_clears_comment(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    signal = _admin_signal(db)
    from app.autotrade import api
    _auth(monkeypatch, api)
    db.upsert_mt5_live_snapshot("80150619", positions=[{
        "identifier": "P2", "ticket": "T2", "signal_code": "",
        "symbol": "XAUUSD.ec", "direction": "LONG", "volume": 0.03,
        "entry_price": 4310, "current_price": 4311, "stop_loss": 4307,
        "take_profit": 0, "profit": 1, "magic": 258025,
        "nexus_managed": True, "order_type": "MARKET",
    }])
    out = api.signal_receipt_mt5_get(
        BackgroundTasks(), int(signal["id"]), "executed", "T2", None,
        "", "80150619", "true", "token",
    )
    assert out["publication"] == "QUEUED"

    with pytest.raises(HTTPException) as exc:
        api.signal_receipt_mt5_get(
            BackgroundTasks(), int(signal["id"]), "executed", "OTHER", None,
            "", "80150619", "true", "token",
        )
    assert exc.value.status_code == 409


def test_stale_publication_claim_is_reclaimed_but_recent_claim_is_not(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    signal = _admin_signal(db)
    assert db.claim_signal_channel(int(signal["id"]), "FREE") is True
    assert db.claim_signal_channel(int(signal["id"]), "FREE") is False
    stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    with db.conn() as con:
        con.execute("UPDATE autotrade_publish_claims SET claimed_at=?", (stale,))
    assert db.claim_signal_channel(int(signal["id"]), "FREE") is True
    db.set_signal_publish_messages(int(signal["id"]), 123, None)
    assert db.claim_signal_channel(int(signal["id"]), "FREE") is False


def test_stale_notification_claim_returns_to_pending_queue(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    signal = _admin_signal(db)
    db.mark_signal_receipt(int(signal["id"]), 400112107, status="rejected", account_number="80150619")
    row = db.pending_autotrade_notifications()[0]
    assert db.claim_autotrade_notification(int(row["id"])) is True
    assert db.pending_autotrade_notifications() == []
    stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    with db.conn() as con:
        con.execute("UPDATE autotrade_notifications SET claimed_at=? WHERE id=?", (stale, int(row["id"])))
    assert [int(x["id"]) for x in db.pending_autotrade_notifications()] == [int(row["id"])]
