from __future__ import annotations

from datetime import datetime, timezone

from app import miniapp_vip_preview


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Conn:
    def __init__(self, rows):
        self.rows = rows
        self.sql = ""
        self.params = ()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=()):
        self.sql = sql
        self.params = params
        return _Cursor(self.rows)


def test_non_vip_preview_exposes_only_locked_symbol_and_status(monkeypatch):
    rows = [
        {"symbol": "XAUUSD", "status": "ACTIVE", "created_at": "2026-09-12T01:00:00+00:00", "closed_at": None},
        {"symbol": "BTCUSDT", "status": "CLOSED", "created_at": "2026-09-12T02:00:00+00:00", "closed_at": "2026-09-12T03:00:00+00:00"},
        {"symbol": "SOLUSDT", "status": "PENDING", "created_at": "2026-09-12T04:00:00+00:00", "closed_at": None},
    ]
    fake = _Conn(rows)
    monkeypatch.setattr(miniapp_vip_preview.db, "current_cycle_id", lambda: "CURRENT")
    monkeypatch.setattr(miniapp_vip_preview.db, "conn", lambda: fake)

    result = miniapp_vip_preview.build_vip_preview(
        has_vip=False,
        now=datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc),
    )

    assert result["summary"] == {"total": 3, "closed": 1, "active": 1, "waiting": 1}
    assert result["cta"]["destination"] == "subscriptions"
    assert result["items"] == [
        {"symbol": "XAUUSD", "status": "ACTIVE", "locked": True},
        {"symbol": "BTCUSDT", "status": "CLOSED", "locked": True},
        {"symbol": "SOLUSDT", "status": "WAITING", "locked": True},
    ]
    for item in result["items"]:
        assert set(item) == {"symbol", "status", "locked"}
    for protected in ("entry_price", "stop_loss", "tp1", "tp2", "tp3", "direction", "profit", "current_price"):
        assert protected not in fake.sql.lower()


def test_vip_member_does_not_receive_locked_preview_rows(monkeypatch):
    fake = _Conn([{"symbol": "XAUUSD", "status": "ACTIVE", "created_at": "2026-09-12T01:00:00+00:00", "closed_at": None}])
    monkeypatch.setattr(miniapp_vip_preview.db, "current_cycle_id", lambda: "CURRENT")
    monkeypatch.setattr(miniapp_vip_preview.db, "conn", lambda: fake)

    result = miniapp_vip_preview.build_vip_preview(
        has_vip=True,
        now=datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc),
    )
    assert result["has_vip"] is True
    assert result["items"] == []
    assert result["cta"] is None


def test_combined_api_mounts_vip_preview_endpoint():
    from app.combined_api import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/miniapp/api/vip-preview" in paths
