
import json
import sqlite3
from pathlib import Path

def _load_db(tmp_path, monkeypatch):
    from app import db
    monkeypatch.setattr(db, "DB_PATH", Path(tmp_path) / "test.db")
    db.init_db()
    with db.conn() as con:
        con.execute("INSERT INTO users(telegram_id,username,first_name,language,joined_public,created_at,updated_at) VALUES(?,?,?,?,1,?,?)", (1,"test","Test","en",db.now_iso(),db.now_iso()))
    return db

def test_trade_event_ledger_keeps_two_updates(monkeypatch, tmp_path):
    db = _load_db(tmp_path, monkeypatch)
    db.enqueue_autotrade_trade_event(1, "UPDATE", {
        "event_id":"evt-1","destination":"VIP","symbol":"XAUUSD","direction":"LONG",
        "volume":0.1,"entry_price":100,"stop_loss":99,"take_profit":102
    }, "7001")
    db.enqueue_autotrade_trade_event(1, "UPDATE", {
        "event_id":"evt-2","destination":"VIP","symbol":"XAUUSD","direction":"LONG",
        "volume":0.1,"entry_price":100,"stop_loss":99.5,"take_profit":102.5
    }, "7001")
    rows=db.autotrade_trade_executions(1)
    assert [r["event_id"] for r in rows] == ["evt-1","evt-2"]
    assert len(db.pending_autotrade_notifications(10)) == 2

def test_duplicate_event_id_is_idempotent(monkeypatch, tmp_path):
    db = _load_db(tmp_path, monkeypatch)
    payload={"event_id":"evt-1","destination":"FREE","symbol":"BTCUSD","direction":"LONG"}
    db.enqueue_autotrade_trade_event(1,"OPEN",payload,"7002")
    db.enqueue_autotrade_trade_event(1,"OPEN",payload,"7002")
    assert len(db.autotrade_trade_executions(1)) == 1
    assert len(db.pending_autotrade_notifications(10)) == 1

def test_daily_stats_uses_execution_ledger(monkeypatch, tmp_path):
    db = _load_db(tmp_path, monkeypatch)
    db.enqueue_autotrade_trade_event(1,"OPEN",{"event_id":"o1","destination":"VIP"},"7003")
    db.update_trade_execution(1,"7003","o1",status="OPEN")
    db.enqueue_autotrade_trade_event(1,"CLOSE",{"event_id":"c1","destination":"VIP","profit":25},"7003")
    db.update_trade_execution(1,"7003","c1",status="CLOSED")
    stats=db.autotrade_user_daily_stats(1,"2000-01-01","2100-01-01")
    assert stats["total"] == 1
    assert stats["closed"] == 1
    assert stats["wins"] == 1


def test_manual_execution_appears_in_history(monkeypatch, tmp_path):
    db = _load_db(tmp_path, monkeypatch)
    db.enqueue_autotrade_trade_event(1,"OPEN",{
        "event_id":"o1","destination":"FREE","symbol":"XAUUSD","direction":"LONG",
        "entry_price":2500,"volume":0.1
    },"7004")
    db.update_trade_execution(1,"7004","o1",status="OPEN")
    rows=db.autotrade_user_signal_receipts(1,limit=20,open_only=False)
    assert any(r["ticket"]=="7004" and r["symbol"]=="XAUUSD" for r in rows)
