from datetime import datetime, timezone
from pathlib import Path
import json


def _fresh_db(monkeypatch, tmp_path):
    from app import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    return db


def test_reconciled_close_is_queued_for_final_telegram_reply(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    uid = 6101
    now = datetime.now(timezone.utc).isoformat()
    with db.conn() as con:
        con.execute(
            "INSERT INTO users(telegram_id,created_at,updated_at) VALUES(?,?,?)",
            (uid, now, now),
        )

    sig = db.create_signal(
        market_type="FOREX", symbol="EURUSD", direction="LONG",
        entry_price=1.1000, stop_loss=1.0950, targets=[1.1100],
        risk_percent=1, rr_ratio=2, destination="VIP",
        chart_file_id=None, created_by=uid, publish_token="SIG-CLOSE-REPLY",
    )
    db.set_signal_publish_messages(int(sig["id"]), None, 4242)
    db.set_signal_status(int(sig["id"]), "ACTIVE")

    item = {
        "event": "CLOSE",
        "ticket": "900100",
        "event_id": "RECON-CLOSE-900100",
        "signal_id": "SIG-CLOSE-REPLY",
        "symbol": "EURUSD",
        "direction": "LONG",
        "volume": 0.1,
        "entry_price": 1.1000,
        "stop_loss": 1.0950,
        "take_profit": 1.1100,
        "exit_price": 1.1080,
        "profit": 80.0,
        "event_time_ms": 1750000000000,
        "destination": "VIP",
    }

    result = db.reconcile_mt5_history(uid, [item])
    assert result["repaired"] == 1
    assert db.get_signal(int(sig["id"]))["status"] == "CLOSED"

    pending = db.pending_autotrade_notifications(10)
    assert len(pending) == 1
    assert pending[0]["event_type"] == "MT5_TRADE_EVENT"
    payload = json.loads(str(pending[0]["payload_json"]))
    assert payload["event"] == "CLOSE"
    assert payload["signal_id"] == "SIG-CLOSE-REPLY"
    assert payload["ticket"] == "900100"

    # Reconciliation retries must not create another final-result work item.
    db.reconcile_mt5_history(uid, [item])
    assert len(db.pending_autotrade_notifications(10)) == 1


def test_closed_status_does_not_suppress_missing_final_reply():
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    start = source.index('    if event == "CLOSE":', source.index("async def _process_mt5_trade_event"))
    end = source.index('    raise ValueError(f"unsupported MT5 event: {event}")', start)
    block = source[start:end]

    assert 'str(row["status"]).upper() == "CLOSED" and close_delivery_complete' in block
    assert "MT5_CLOSE_DELIVERY" in block
    assert 'destination == "BOTH" and free_mid is not None and vip_mid is not None' in block
    assert "MT5 CLOSE Telegram reply incomplete" in block
    assert "_publish_result_with_fallback" in block


def test_final_result_sender_uses_reply_parameters():
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    start = source.index("async def _publish_result_to_channel")
    end = source.index("\n\nasync def ", start)
    block = source[start:end]
    assert "bot.send_message" in block
    assert "ReplyParameters(message_id=int(parent_message_id))" in block


def test_final_result_prefers_original_signal_anchor():
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    start = source.index("async def _publish_result_with_fallback")
    end = source.index("\n\nasync def ", start)
    block = source[start:end]
    assert "for raw in (original_message_id, last_message_id):" in block
