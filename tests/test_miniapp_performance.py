from __future__ import annotations

from datetime import datetime, timezone

from app import miniapp_vip_preview
from app.miniapp_performance import _r_overview, _safe_summary, _visible_trade
from app.services.analytics_service import _r_metrics, _realized_r


class _PreviewCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _PreviewConn:
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
        return _PreviewCursor(self.rows)


def test_track_record_summary_does_not_expose_raw_return_like_metrics():
    item = _safe_summary({
        "total": 10,
        "wins": 6,
        "losses": 3,
        "be": 1,
        "win_rate": 60.0,
        "net_pct": 48.2,
        "crypto_pct": 31.0,
        "forex_pips": 220.0,
    })
    assert item == {"total": 10, "wins": 6, "losses": 3, "be": 1, "win_rate": 60.0}
    assert "net_pct" not in item
    assert "crypto_pct" not in item
    assert "forex_pips" not in item


def test_canonical_r_metrics_include_losses_streak_and_peak_to_trough_drawdown():
    rows = [
        {"entry_price": 100, "stop_loss": 90, "exit_price": 110, "direction": "BUY", "closed_at": "2026-01-01T00:00:00+00:00"},
        {"entry_price": 100, "stop_loss": 90, "exit_price": 90, "direction": "BUY", "closed_at": "2026-01-02T00:00:00+00:00"},
        {"entry_price": 100, "stop_loss": 90, "exit_price": 90, "direction": "BUY", "closed_at": "2026-01-03T00:00:00+00:00"},
        {"entry_price": 100, "stop_loss": 90, "exit_price": 120, "direction": "BUY", "closed_at": "2026-01-04T00:00:00+00:00"},
    ]
    metrics = _r_metrics(rows)
    assert metrics["r_sample_size"] == 4
    assert metrics["r_missing_count"] == 0
    assert metrics["r_complete"] is True
    assert metrics["net_r"] == 1.0
    assert metrics["average_realized_r"] == 0.25
    assert metrics["profit_factor_r"] == 1.5
    assert metrics["current_losing_streak"] == 0
    assert metrics["maximum_losing_streak"] == 2
    assert metrics["max_drawdown_r"] == -2.0
    assert metrics["equity_curve_r"] == [1.0, 0.0, -1.0, 1.0]


def test_r_metrics_fail_safe_when_required_trade_data_is_missing():
    metrics = _r_metrics([
        {"entry_price": 100, "stop_loss": None, "exit_price": 110, "direction": "BUY", "closed_at": "2026-01-01T00:00:00+00:00"}
    ])
    assert metrics["r_sample_size"] == 0
    assert metrics["r_missing_count"] == 1
    assert metrics["r_complete"] is False
    assert metrics["net_r"] is None
    assert metrics["profit_factor_r"] is None
    assert metrics["max_drawdown_r"] is None


def test_partial_close_without_explicit_r_is_not_reconstructed_from_final_exit():
    row = {
        "entry_price": 100,
        "stop_loss": 90,
        "exit_price": 120,
        "direction": "BUY",
        "result_value": 20,
        "result_unit": "PIPS",
        "has_partial": 1,
    }
    assert _realized_r(row) is None


def test_explicit_r_remains_usable_for_partial_close_result():
    row = {
        "entry_price": 100,
        "stop_loss": 90,
        "exit_price": 120,
        "direction": "BUY",
        "result_value": 1.4,
        "result_unit": "R",
        "has_partial": 1,
    }
    assert _realized_r(row) == 1.4


def test_overview_suppresses_r_metrics_when_period_coverage_is_incomplete():
    risk = _r_overview({
        "total": 4,
        "r_sample_size": 3,
        "r_missing_count": 1,
        "r_complete": False,
        "net_r": 2.0,
        "profit_factor_r": 2.5,
        "max_drawdown_r": -1.0,
    })
    assert risk["status"] == "INSUFFICIENT_DATA"
    assert risk["sample_size"] == 3
    assert risk["total_trades"] == 4
    assert risk["missing_count"] == 1
    assert risk["net_r"] is None
    assert risk["profit_factor"] is None
    assert risk["max_drawdown_r"] is None


def test_non_vip_locked_trade_does_not_expose_premium_levels():
    source = {
        "id": 7,
        "code": "NX-7",
        "symbol": "XAUUSD",
        "access": "VIP",
        "status": "CLOSED",
        "close_time": "2026-01-01T01:00:00+00:00",
        "result_value": 1.7,
        "result_unit": "R",
        "realized_r": 1.7,
        "result_source": "CALCULATED",
        "initial_entry": 3642,
        "initial_sl": 3635,
        "initial_tp": 3649,
        "final_exit": 3658,
    }
    item = _visible_trade(source, has_vip=False)
    assert item["locked"] is True
    for protected in ("initial_entry", "initial_sl", "initial_tp", "final_exit"):
        assert protected not in item


def test_non_vip_vip_preview_exposes_only_locked_activity(monkeypatch):
    rows = [
        {"symbol": "XAUUSD", "status": "ACTIVE", "created_at": "2026-09-12T01:00:00+00:00", "closed_at": None},
        {"symbol": "BTCUSDT", "status": "CLOSED", "created_at": "2026-09-12T02:00:00+00:00", "closed_at": "2026-09-12T03:00:00+00:00"},
        {"symbol": "SOLUSDT", "status": "PENDING", "created_at": "2026-09-12T04:00:00+00:00", "closed_at": None},
    ]
    fake = _PreviewConn(rows)
    monkeypatch.setattr(miniapp_vip_preview.db, "current_cycle_id", lambda: "CURRENT")
    monkeypatch.setattr(miniapp_vip_preview.db, "conn", lambda: fake)
    result = miniapp_vip_preview.build_vip_preview(
        has_vip=False,
        now=datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc),
    )
    assert result["summary"] == {"total": 3, "closed": 1, "active": 1, "waiting": 1}
    assert result["items"] == [
        {"symbol": "XAUUSD", "status": "ACTIVE", "locked": True},
        {"symbol": "BTCUSDT", "status": "CLOSED", "locked": True},
        {"symbol": "SOLUSDT", "status": "WAITING", "locked": True},
    ]
    assert result["cta"]["destination"] == "subscriptions"
    for item in result["items"]:
        assert set(item) == {"symbol", "status", "locked"}
    for protected in ("entry_price", "stop_loss", "tp1", "tp2", "tp3", "direction", "profit", "current_price"):
        assert protected not in fake.sql.lower()


def test_combined_api_exposes_additive_performance_resources():
    from app.combined_api import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/miniapp/api/performance/details" in paths
    assert "/miniapp/api/performance/overview" in paths
    assert "/miniapp/api/performance/trades" in paths
    assert "/miniapp/api/performance/trades/{trade_id}" in paths
    assert "/miniapp/api/performance/methodology" in paths
    assert "/miniapp/api/vip-preview" in paths
