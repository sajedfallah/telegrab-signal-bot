from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from app import miniapp_signals


def _signal(*, direction: str = "BUY") -> dict:
    return {
        "id": 77,
        "code": "SIG-77",
        "status": "ACTIVE",
        "issuer_account": "100200300",
        "entry_price": 100.0,
        "stop_loss": 90.0 if direction == "BUY" else 110.0,
        "direction": direction,
    }


def _fake_db(monkeypatch, live_rows: list[dict], executions: list[dict] | None = None):
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        CREATE TABLE mt5_live_state (
            account_number TEXT NOT NULL,
            state_type TEXT NOT NULL,
            ticket TEXT NOT NULL,
            signal_code TEXT,
            nexus_managed INTEGER NOT NULL DEFAULT 0,
            status TEXT,
            symbol TEXT,
            direction TEXT,
            volume REAL,
            entry_price REAL,
            current_price REAL,
            stop_loss REAL,
            take_profit REAL,
            profit REAL,
            last_seen_at TEXT
        );
        CREATE TABLE autotrade_trade_executions (
            signal_id INTEGER,
            ticket TEXT
        );
        """
    )
    for row in live_rows:
        con.execute(
            """
            INSERT INTO mt5_live_state(
                account_number,state_type,ticket,signal_code,nexus_managed,status,
                symbol,direction,volume,entry_price,current_price,stop_loss,
                take_profit,profit,last_seen_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row.get("account_number", "100200300"), row.get("state_type", "POSITION"),
                str(row.get("ticket", "9001")), row.get("signal_code", "SIG-77"),
                int(row.get("nexus_managed", 1)), row.get("status", "OPEN"),
                row.get("symbol", "XAUUSD"), row.get("direction", "BUY"),
                row.get("volume", 0.02), row.get("entry_price", 100.0),
                row.get("current_price", 115.0), row.get("stop_loss", 90.0),
                row.get("take_profit", 130.0), row.get("profit", 12.4),
                row.get("last_seen_at", datetime.now(timezone.utc).isoformat()),
            ),
        )
    for row in executions or []:
        con.execute(
            "INSERT INTO autotrade_trade_executions(signal_id,ticket) VALUES(?,?)",
            (int(row["signal_id"]), str(row["ticket"])),
        )
    con.commit()

    @contextmanager
    def fake_conn():
        yield con

    monkeypatch.setattr(miniapp_signals.db, "conn", fake_conn)
    return con


def test_live_signal_state_uses_broker_profit_and_initial_r(monkeypatch):
    con = _fake_db(monkeypatch, [{"current_price": 115.0, "profit": 12.4, "volume": 0.02}])
    try:
        live = miniapp_signals._live_signal_state(_signal())
    finally:
        con.close()

    assert live is not None
    assert live["status"] == "LIVE"
    assert live["current_price"] == 115.0
    assert live["floating_pnl"] == 12.4
    assert live["current_r"] == 1.5
    assert live["volume"] == 0.02
    assert live["pnl_state"] == "IN_PROFIT"


def test_live_signal_state_marks_old_snapshot_stale(monkeypatch):
    monkeypatch.setattr(miniapp_signals, "ACTIVE_TRUTH_STALE_SECONDS", 120)
    old = (datetime.now(timezone.utc) - timedelta(seconds=121)).isoformat()
    con = _fake_db(monkeypatch, [{"last_seen_at": old, "profit": -3.25, "current_price": 97.0}])
    try:
        live = miniapp_signals._live_signal_state(_signal())
    finally:
        con.close()

    assert live is not None
    assert live["status"] == "STALE"
    assert live["floating_pnl"] == -3.25
    assert live["pnl_state"] == "IN_LOSS"
    assert live["age_seconds"] >= 120


def test_live_signal_state_supports_execution_ticket_fallback(monkeypatch):
    con = _fake_db(
        monkeypatch,
        [{"ticket": "9002", "signal_code": "", "profit": 5.0, "current_price": 105.0}],
        executions=[{"signal_id": 77, "ticket": "9002"}],
    )
    try:
        live = miniapp_signals._live_signal_state(_signal())
    finally:
        con.close()

    assert live is not None
    assert live["status"] == "LIVE"
    assert live["floating_pnl"] == 5.0
    assert live["current_r"] == 0.5


def test_pending_order_does_not_fake_floating_profit(monkeypatch):
    con = _fake_db(
        monkeypatch,
        [{"state_type": "ORDER", "status": "PENDING", "profit": 999.0, "current_price": 99.0, "volume": 0.03}],
    )
    try:
        live = miniapp_signals._live_signal_state(_signal())
    finally:
        con.close()

    assert live is not None
    assert live["status"] == "PENDING"
    assert live["floating_pnl"] == 0.0
    assert live["current_r"] is None
    assert live["volume"] == 0.03


def test_closed_signal_has_no_live_snapshot(monkeypatch):
    con = _fake_db(monkeypatch, [{"profit": 10.0}])
    signal = _signal()
    signal["status"] = "CLOSED"
    try:
        assert miniapp_signals._live_signal_state(signal) is None
    finally:
        con.close()
