from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from app import miniapp_signals
from app.miniapp_home import NEXUS_ENTRY_URL


class _FakeRows:
    def __init__(self, owner, one=None):
        self.owner = owner
        self.one = one

    def fetchall(self):
        return []

    def fetchone(self):
        return self.one


class _FakeConn:
    def __init__(self, one=None):
        self.sql = ""
        self.params = ()
        self.one = one

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=()):
        self.sql = sql
        self.params = params
        return _FakeRows(self, self.one)


def _vip_active_row() -> dict:
    return {
        "id": 91,
        "code": "NX-0091",
        "cycle_id": "CYCLE-TEST",
        "market_type": "FOREX",
        "symbol": "XAUUSD",
        "timeframe": "5M",
        "direction": "BUY",
        "entry_price": 3500.0,
        "stop_loss": 3490.0,
        "risk_percent": 1.0,
        "rr_ratio": 2.0,
        "destination": "VIP",
        "order_type": "MARKET",
        "status": "ACTIVE",
        "created_at": "2026-09-10T00:00:00+00:00",
        "closed_at": None,
        "result_value": None,
        "result_unit": None,
    }


def test_active_state_excludes_draft_and_terminal_records():
    sql, _ = miniapp_signals._state_clause("ACTIVE")
    for status in ("DRAFT", "CLOSED", "REJECTED", "CANCELLED", "EXPIRED", "PUBLISH_FAILED"):
        assert status in sql


def test_active_mt5_truth_clause_requires_current_broker_snapshot():
    sql, args = miniapp_signals._active_truth_clause("ACTIVE")
    assert "mt5_live_state" in sql
    assert "OPEN" in sql and "PENDING" in sql
    assert "nexus_managed" in sql
    assert "last_seen_at" in sql
    assert len(args) == 1


def test_non_vip_active_feed_filters_vip_only_rows_at_sql_layer(monkeypatch):
    fake = _FakeConn()
    monkeypatch.setattr(miniapp_signals, "_auth_user", lambda _: {"id": 123})
    monkeypatch.setattr(miniapp_signals, "_entitlements", lambda _: {"vip": False})
    monkeypatch.setattr(miniapp_signals.db, "current_cycle_id", lambda: "CYCLE-TEST")
    monkeypatch.setattr(miniapp_signals.db, "conn", lambda: fake)

    result = miniapp_signals.signals(
        state="ACTIVE",
        access="ALL",
        limit=20,
        offset=0,
        x_telegram_init_data="signed",
    )

    assert result["items"] == []
    assert "<> 'VIP'" in fake.sql
    assert "DRAFT" in fake.sql
    assert "mt5_live_state" in fake.sql


def test_non_vip_cannot_open_active_vip_signal_detail(monkeypatch):
    monkeypatch.setattr(miniapp_signals, "_auth_user", lambda _: {"id": 123})
    monkeypatch.setattr(miniapp_signals, "_entitlements", lambda _: {"vip": False, "autotrade": False})
    monkeypatch.setattr(miniapp_signals.db, "current_cycle_id", lambda: "CYCLE-TEST")
    monkeypatch.setattr(miniapp_signals.db, "get_signal", lambda _: _vip_active_row())

    with pytest.raises(HTTPException) as exc:
        miniapp_signals.signal_detail(91, x_telegram_init_data="signed")
    assert exc.value.status_code == 403
    assert exc.value.detail == "VIP access required"


def test_stale_mt5_admin_active_signal_detail_is_hidden(monkeypatch):
    row = _vip_active_row() | {"destination": "FREE", "issuer_type": "MT5_ADMIN", "issuer_account": "10001"}
    fake = _FakeConn(one=None)
    monkeypatch.setattr(miniapp_signals, "_auth_user", lambda _: {"id": 123})
    monkeypatch.setattr(miniapp_signals, "_entitlements", lambda _: {"vip": False, "autotrade": False})
    monkeypatch.setattr(miniapp_signals.db, "current_cycle_id", lambda: "CYCLE-TEST")
    monkeypatch.setattr(miniapp_signals.db, "get_signal", lambda _: row)
    monkeypatch.setattr(miniapp_signals.db, "conn", lambda: fake)

    with pytest.raises(HTTPException) as exc:
        miniapp_signals.signal_detail(91, x_telegram_init_data="signed")
    assert exc.value.status_code == 404
    assert exc.value.detail == "signal is no longer active"
    assert "mt5_live_state" in fake.sql


def test_closed_signal_has_explicit_profit_or_loss_label(monkeypatch):
    monkeypatch.setattr(miniapp_signals, "_targets", lambda _: [])
    row = _vip_active_row() | {
        "destination": "FREE",
        "status": "CLOSED",
        "closed_at": "2026-09-10T01:00:00+00:00",
        "result_value": -18.5,
        "result_unit": "PIPS",
    }
    item = miniapp_signals.serialize_signal(row, has_vip=False)
    assert item["result"] == "LOSS"
    assert item["result_value"] == -18.5
    assert item["result_label_fa"] == "ضرر -18.5 PIPS"


def test_closed_signal_without_result_is_not_misreported_as_break_even(monkeypatch):
    monkeypatch.setattr(miniapp_signals, "_targets", lambda _: [])
    row = _vip_active_row() | {
        "destination": "FREE",
        "status": "CLOSED",
        "closed_at": "2026-09-10T01:00:00+00:00",
        "result_value": None,
    }
    item = miniapp_signals.serialize_signal(row, has_vip=False)
    assert item["result"] == "UNKNOWN"
    assert item["result_label_fa"] == "نتیجه ثبت نشده"


def test_enter_nexus_link_is_global_and_fixed():
    assert NEXUS_ENTRY_URL == "https://t.me/nexus_publicc"


def test_miniapp_shell_loads_official_logo_svg_icons_and_design_layer():
    html = Path("miniapp/index.html").read_text(encoding="utf-8")
    assert "./assets/brand/nexus-logo.svg" in html
    assert "./icons.js" in html
    assert "./design-v2.css" in html
    assert "./account-v2.js" in html
    assert "./ui-fixes.js" in html
