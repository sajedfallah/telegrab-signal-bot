from datetime import datetime, timezone

from app.agent_system.contracts import MarketSnapshot, WorkflowState
from app.agent_system.scanner import scan


def _candles(base: float = 100.0):
    rows = []
    for i in range(40):
        close = base + i * 0.02
        rows.append({"time": 1_700_000_000 + i * 300, "open": close - 0.05, "high": close + 0.10, "low": close - 0.10, "close": close, "tick_volume": 10.0})
    return tuple(rows)


def _snapshot(**overrides):
    rows = _candles()
    data = {
        "snapshot_id": "snap-scanner-test-0001",
        "symbol": "US30",
        "as_of": datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc),
        "source": "MT5_MARKET_FEED",
        "timeframes": {"H1": rows, "M15": rows, "M5": rows},
        "bid": 100.77,
        "ask": 100.79,
        "session": "LONDON",
        "data_freshness_ms": 1000,
    }
    data.update(overrides)
    return MarketSnapshot(**data)


def test_scanner_fails_closed_on_stale_data():
    decision = scan(_snapshot(data_freshness_ms=60_000))
    assert decision.state == WorkflowState.NO_TRADE
    assert "stale_market_data" in decision.blocks


def test_scanner_fails_closed_when_required_timeframe_missing():
    rows = _candles()
    decision = scan(_snapshot(timeframes={"H1": rows, "M15": rows, "M5": rows[:10]}))
    assert decision.state == WorkflowState.NO_TRADE
    assert "insufficient_m5_candles" in decision.blocks


def test_scanner_waits_when_no_objective_event_exists():
    rows = _candles()
    flat = tuple({**x, "high": 101.5, "low": 99.5, "open": 100.5, "close": 100.5} for x in rows)
    decision = scan(_snapshot(timeframes={"H1": flat, "M15": flat, "M5": flat}, bid=100.49, ask=100.51))
    assert decision.state == WorkflowState.WAIT
    assert not decision.blocks


def test_scanner_watch_is_not_signal_candidate():
    rows = list(_candles())
    prior_low = min(float(x["low"]) for x in rows[-14:-2])
    rows[-2] = {**rows[-2], "low": prior_low - 0.5, "close": prior_low + 0.05}
    m5 = tuple(rows)
    decision = scan(_snapshot(timeframes={"H1": _candles(), "M15": _candles(), "M5": m5}))
    assert decision.state == WorkflowState.WATCH
    assert decision.state != WorkflowState.SIGNAL_CANDIDATE
    assert "m5_sell_side_sweep_reclaim" in decision.triggers
