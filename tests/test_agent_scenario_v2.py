from datetime import datetime, timezone

from app.agent_system.contracts import MarketSnapshot
from app.agent_system.scenario_v2 import build_shadow_scenarios, format_shadow_scenarios


def snapshot(*, freshness=0):
    rows = tuple({"open": 100.5, "high": 101.0 + i * 0.01,
                  "low": 99.0 - i * 0.01, "close": 100.0}
                 for i in range(25))
    return MarketSnapshot(
        snapshot_id="snapshot-v2-test", symbol="XAUUSD", as_of=datetime.now(timezone.utc),
        source="test", timeframes={"M1": rows}, bid=100.0, ask=100.2,
        data_freshness_ms=freshness,
    )


def test_v2_watch_has_correct_sweep_sides_and_no_guessed_prices():
    result = build_shadow_scenarios(snapshot(), "M1")
    assert result["status"] == "WATCH"
    assert result["long"]["sweep"] == "SELL_SIDE"
    assert result["short"]["sweep"] == "BUY_SIDE"
    assert result["entry"] is None
    assert result["stop_loss"] is None
    assert result["take_profits"] == []
    assert result["rr"] is None
    assert result["execution_allowed"] is False
    assert "Entry / SL / TP / RR" in format_shadow_scenarios(result)


def test_v2_stale_data_fails_closed():
    result = build_shadow_scenarios(snapshot(freshness=40_000), "M1")
    assert result["status"] == "WAIT"
    assert result["reference_levels"] == {}
    assert "missing_or_stale_market_data" in result["blocks"]
    assert result["entry"] is None
