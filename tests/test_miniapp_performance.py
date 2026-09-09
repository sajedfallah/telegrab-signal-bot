from __future__ import annotations

from app.miniapp_performance import _safe_summary


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


def test_combined_api_exposes_track_record_detail_resource():
    from app.combined_api import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/miniapp/api/performance/details" in paths
