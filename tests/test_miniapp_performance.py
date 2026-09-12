from __future__ import annotations

from app.miniapp_performance import _safe_summary, _visible_trade
from app.services.analytics_service import _r_metrics


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
    assert metrics["net_r"] is None
    assert metrics["profit_factor_r"] is None
    assert metrics["max_drawdown_r"] is None


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


def test_combined_api_exposes_additive_performance_resources():
    from app.combined_api import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/miniapp/api/performance/details" in paths
    assert "/miniapp/api/performance/overview" in paths
    assert "/miniapp/api/performance/trades" in paths
    assert "/miniapp/api/performance/trades/{trade_id}" in paths
    assert "/miniapp/api/performance/methodology" in paths
