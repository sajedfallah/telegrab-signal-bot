from datetime import datetime, timezone

from app.agent_system.agents.ict import assess_ict
from app.agent_system.contracts import Direction, MarketSnapshot


def _trend_rows(direction: str, count: int = 50):
    rows = []
    for i in range(count):
        base = 100 + (i * 0.3 if direction == "up" else -i * 0.3)
        rows.append({"time": 1_700_000_000 + i * 300, "open": base - 0.05, "high": base + 0.2, "low": base - 0.2, "close": base + 0.05, "tick_volume": 10.0})
    return rows


def _bull_trigger_rows():
    rows = _trend_rows("up")
    prior_low = min(x["low"] for x in rows[-14:-2])
    rows[-2] = {**rows[-2], "low": prior_low - 1.0, "close": prior_low + 0.1}
    breakout = max(x["high"] for x in rows[-7:-1]) + 0.5
    rows[-1] = {**rows[-1], "high": breakout + 0.2, "close": breakout}
    return rows


def _snapshot(h1=None, m15=None, m5=None, **overrides):
    h1 = h1 or _trend_rows("up")
    m15 = m15 or _trend_rows("up")
    m5 = m5 or _bull_trigger_rows()
    data = {
        "snapshot_id": "snap-ict-test-0001",
        "symbol": "XAUUSD",
        "as_of": datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc),
        "source": "MT5_MARKET_FEED",
        "timeframes": {"H1": tuple(h1), "M15": tuple(m15), "M5": tuple(m5)},
        "bid": 114.7, "ask": 114.9, "session": "LONDON", "data_freshness_ms": 1000,
    }
    data.update(overrides)
    return MarketSnapshot(**data)


def test_ict_long_requires_h1_and_m5_alignment():
    result = assess_ict(_snapshot())
    assert result.direction == Direction.LONG
    assert result.confidence is None
    assert any("5M sell-side" in x for x in result.evidence)


def test_ict_does_not_force_trade_without_trigger():
    result = assess_ict(_snapshot(m5=_trend_rows("up")))
    assert result.direction == Direction.NEUTRAL
    assert any("confirmation required" in x for x in result.invalidations)


def test_ict_fails_closed_on_stale_snapshot():
    result = assess_ict(_snapshot(data_freshness_ms=60_000))
    assert result.direction == Direction.NEUTRAL
    assert "stale_market_data" in result.missing_data


def test_ict_does_not_treat_quadrant_as_entry():
    result = assess_ict(_snapshot())
    assert any("Quadrant" in x and "not yet attached" in x for x in result.evidence)
