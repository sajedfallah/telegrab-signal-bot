import pytest

from app.agent_system.tradingview_capture import (
    TradingViewCaptureError,
    _tv_interval,
    capture_tradingview_chart,
)


def test_supported_timeframes():
    assert _tv_interval("M1") == "1"
    assert _tv_interval("M5") == "5"
    assert _tv_interval("H1") == "60"
    assert _tv_interval("D1") == "D"


def test_rejects_unknown_timeframe():
    with pytest.raises(TradingViewCaptureError):
        _tv_interval("M2")


@pytest.mark.asyncio
async def test_capture_is_opt_in(monkeypatch):
    monkeypatch.delenv("NEXUS_AGENT_CHART_SOURCE", raising=False)
    with pytest.raises(TradingViewCaptureError, match="tradingview_not_enabled"):
        await capture_tradingview_chart("XAUUSD", "M1")
