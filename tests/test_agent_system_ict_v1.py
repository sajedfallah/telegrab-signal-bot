from datetime import datetime, timezone

from app.agent_system.agents.ict import assess_ict
from app.agent_system.contracts import Direction, MarketSnapshot


def _trend_rows(direction: str, count: int = 50):
    rows = []
    for i in range(count):
        base = 100 + (i * 0.3 if direction == "up" else -i * 0.3)
        rows.append({"time": 1_700_000_000 + i * 300, "open": base - 0.05, "high": base + 0.2, "low": base - 0.2, "close": base + 0.05, "tick_volume": 10.0})
    return rows


def _daily_rows(count: int = 20):
    rows = _trend_rows("up", count)
    # Give the last ten closed D1 candles real wicks so the NEXUS Daily
    # Quadrant engine has deterministic context without creating an entry.
    rows[-3] = {**rows[-3], "high": rows[-3]["high"] + 1.5}
    return rows


def _bull_trigger_rows():
    rows = _trend_rows("up")
    prior_low = min(x["low"] for x in rows[-14:-2])
    rows[-2] = {**rows[-2], "low": prior_low - 1.0, "close": prior_low + 0.1}
    breakout = max(x["high"] for x in rows[-7:-1]) + 0.5
    rows[-1] = {**rows[-1], "high": breakout + 0.2, "close": breakout}
    return rows





def _bull_delayed_trigger_rows():
    rows = _trend_rows("up")
    sweep_index = len(rows) - 4
    prior_low = min(x["low"] for x in rows[sweep_index - 12:sweep_index])
    rows[sweep_index] = {**rows[sweep_index], "low": prior_low - 1.0, "close": prior_low + 0.1}
    breakout = max(x["high"] for x in rows[-7:-1]) + 0.5
    rows[-1] = {**rows[-1], "high": breakout + 0.2, "close": breakout}
    return rows


def _bull_expired_sweep_rows():
    rows = _trend_rows("up")
    sweep_index = len(rows) - 7
    prior_low = min(x["low"] for x in rows[sweep_index - 12:sweep_index])
    rows[sweep_index] = {**rows[sweep_index], "low": prior_low - 1.0, "close": prior_low + 0.1}
    breakout = max(x["high"] for x in rows[-7:-1]) + 0.5
    rows[-1] = {**rows[-1], "high": breakout + 0.2, "close": breakout}
    return rows
\ndef _snapshot(d1=None, h1=None, m15=None, m5=None, **overrides):
    d1 = d1 or _daily_rows()
    h1 = h1 or _trend_rows("up")
    m15 = m15 or _trend_rows("up")
    m5 = m5 or _bull_trigger_rows()
    data = {
        "snapshot_id": "snap-ict-test-0001",
        "symbol": "XAUUSD",
        "as_of": datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc),
        "source": "MT5_MARKET_FEED",
        "timeframes": {"D1": tuple(d1), "H1": tuple(h1), "M15": tuple(m15), "M5": tuple(m5)},
        "bid": 114.7, "ask": 114.9, "session": "LONDON", "data_freshness_ms": 1000,
    }
    data.update(overrides)
    return MarketSnapshot(**data)


def test_ict_long_requires_h1_and_m5_alignment():
    result = assess_ict(_snapshot())
    assert result.direction == Direction.LONG
    assert result.confidence is None
    assert any("5M sell-side" in x for x in result.evidence)
    assert any("Daily Quadrant" in x for x in result.evidence)


def test_ict_does_not_force_trade_without_trigger():
    result = assess_ict(_snapshot(m5=_trend_rows("up")))
    assert result.direction == Direction.NEUTRAL
    assert any("confirmation required" in x for x in result.invalidations)


def test_ict_fails_closed_on_stale_snapshot():
    result = assess_ict(_snapshot(data_freshness_ms=60_000))
    assert result.direction == Direction.NEUTRAL
    assert "stale_market_data" in result.missing_data


def test_ict_fails_closed_without_daily_context():
    result = assess_ict(_snapshot(timeframes={"H1": tuple(_trend_rows("up")), "M15": tuple(_trend_rows("up")), "M5": tuple(_bull_trigger_rows())}))
    assert result.direction == Direction.NEUTRAL
    assert "candles:D1" in result.missing_data


def test_quadrant_context_alone_does_not_create_entry():
    result = assess_ict(_snapshot(m5=_trend_rows("up")))
    assert any("Daily Quadrant" in x for x in result.evidence)
    assert result.direction == Direction.NEUTRAL



def test_ict_accepts_recent_sweep_followed_by_delayed_mss():
    result = assess_ict(_snapshot(m5=_bull_delayed_trigger_rows()))
    assert result.direction == Direction.LONG
    assert any("sell-side liquidity sweep/reclaim (3 bars before MSS check)" in x for x in result.evidence)
    assert any("bullish displacement/MSS" in x for x in result.evidence)


def test_ict_does_not_reuse_expired_sweep_for_new_mss():
    result = assess_ict(_snapshot(m5=_bull_expired_sweep_rows()))
    assert result.direction == Direction.NEUTRAL
    assert not any("sell-side liquidity sweep/reclaim" in x for x in result.evidence)
    assert any("bullish displacement/MSS" in x for x in result.evidence)
