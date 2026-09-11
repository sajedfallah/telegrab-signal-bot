from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app import miniapp_admin_api
from app.miniapp_admin_api import CreateSignalRequest


def _base_request(**overrides):
    payload = {
        "symbol": "XAUUSD",
        "direction": "BUY",
        "entry": 3650.0,
        "stop_loss": 3645.0,
        "stop_loss_mode": "MANUAL",
        "take_profit_mode": "AUTO",
        "destination": "VIP",
        "request_id": "v066-contract-001",
        "timeframe": "M5",
        "setup_mode": "MANUAL",
        "volume_mode": "RISK",
        "risk_percent": 1.0,
        "lot_size": None,
        "trailing_enabled": True,
        "trailing_profile_code": "NEXUS_TRAIL_07",
        "digits": 2,
    }
    payload.update(overrides)
    return payload


def test_auto_setup_contract_is_fail_closed_until_structure_engine_exists():
    with pytest.raises(ValidationError, match="confirmed MT5 candle structure"):
        CreateSignalRequest(**_base_request(setup_mode="AUTO"))


def test_manual_setup_keeps_production_fixed_lot_and_trailing_contract():
    request = CreateSignalRequest(**_base_request(
        setup_mode="MANUAL",
        volume_mode="FIXED",
        risk_percent=0.0,
        lot_size=0.03,
    ))
    assert request.setup_mode == "MANUAL"
    assert request.volume_mode == "FIXED"
    assert request.lot_size == 0.03
    assert request.trailing_profile_code == "NEXUS_TRAIL_07"


def test_risk_mode_rejects_ambiguous_fixed_lot():
    with pytest.raises(ValidationError, match="lot_size must be empty"):
        CreateSignalRequest(**_base_request(volume_mode="RISK", lot_size=0.02))


def test_admin_live_state_uses_broker_profit_without_recalculation(monkeypatch):
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
    con.execute(
        """
        INSERT INTO mt5_live_state(
            account_number,state_type,ticket,signal_code,nexus_managed,status,
            symbol,direction,volume,entry_price,current_price,stop_loss,
            take_profit,profit,last_seen_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "100200300", "POSITION", "9001", "SIG-77", 1, "OPEN",
            "XAUUSD", "BUY", 0.02, 100.0, 115.0, 90.0, 130.0,
            12.4, datetime.now(timezone.utc).isoformat(),
        ),
    )
    con.commit()

    @contextmanager
    def fake_conn():
        yield con

    monkeypatch.setattr(miniapp_admin_api.db, "conn", fake_conn)
    signal = {
        "id": 77,
        "code": "SIG-77",
        "status": "ACTIVE",
        "issuer_account": "100200300",
        "entry_price": 100.0,
        "stop_loss": 90.0,
        "direction": "BUY",
    }
    try:
        live = miniapp_admin_api._admin_live_signal(signal)
    finally:
        con.close()

    assert live is not None
    assert live["status"] == "LIVE"
    assert live["floating_pnl"] == 12.4
    assert live["current_price"] == 115.0
    assert live["current_r"] == 1.5
    assert live["volume"] == 0.02


def test_reconcile_ui_loads_overlay_and_customer_live_assets_are_cache_busted():
    admin_html = Path("miniapp/admin.html").read_text(encoding="utf-8")
    customer_html = Path("miniapp/index.html").read_text(encoding="utf-8")
    overlay_js = Path("miniapp/admin-v066-overlay.js").read_text(encoding="utf-8")

    assert "/miniapp/admin-v066-overlay.css?v=1" in admin_html
    assert "/miniapp/admin-v066-overlay.js?v=1" in admin_html
    assert "AUTO SETUP" in overlay_js
    assert "Fail-Closed" in overlay_js
    assert "FLOATING P&amp;L" in overlay_js
    assert "signals-v2.js?v=20260912-0212" in customer_html
    assert "signals-v2.css?v=20260912-0212" in customer_html
