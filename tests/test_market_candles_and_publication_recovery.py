from __future__ import annotations

from pathlib import Path

import pytest

from app.market_candles import CandlePoint, CandleSeries, MarketFeedRequest, _tf


def _text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_market_timeframe_contract_is_exact_and_small():
    assert _tf("1m") == "M1"
    assert _tf("5m") == "M5"
    assert _tf("15m") == "M15"
    assert _tf("1h") == "H1"
    assert _tf("1D") == "D1"
    with pytest.raises(ValueError):
        _tf("H4")


def test_candle_validation_rejects_impossible_ohlc():
    with pytest.raises(ValueError):
        CandlePoint(time=1_700_000_000, open=1.10, high=1.05, low=1.00, close=1.02)


def test_market_feed_request_supports_gold_and_forex_series():
    candle = CandlePoint(time=1_700_000_000, open=2000, high=2002, low=1998, close=2001)
    req = MarketFeedRequest(
        account_number="80150619",
        series=[
            CandleSeries(symbol="XAUUSD", timeframe="M5", candles=[candle]),
            CandleSeries(symbol="EURUSD", timeframe="5m", candles=[
                CandlePoint(time=1_700_000_000, open=1.1, high=1.2, low=1.0, close=1.15)
            ]),
        ],
    )
    assert req.series[0].timeframe == "M5"
    assert req.series[1].timeframe == "M5"


def test_combined_api_installs_market_feed_and_publication_recovery_after_execution_gate():
    src = _text("app/combined_api.py")
    assert "market_candles_router" in src
    assert "install_miniapp_execution_gate(app)" in src
    assert "install_publication_recovery(app)" in src
    assert src.index("install_miniapp_execution_gate(app)") < src.index("install_publication_recovery(app)")


def test_publication_recovery_requires_broker_receipt_before_chart_fallback():
    src = _text("app/autotrade/publication_recovery_runtime.py")
    assert "_accepted_receipt(signal_id)" in src
    assert "allow_without_chart=True" in src
    assert "PUBLICATION_FALLBACK_QUEUED" in src
    assert "FAILED" in src and "EXPIRED" in src


def test_forex_frontend_uses_mt5_market_candle_endpoint_without_fake_fallback():
    src = _text("miniapp/live-charts-forex.js")
    assert "/miniapp/api/market-candles" in src
    assert "NEXUS / MT5" in src
    assert "داده ساختگی نمایش داده نمی‌شود" in src
    for symbol in ("XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"):
        assert symbol in src


def test_market_feed_ea_sends_only_admin_authenticated_broker_candles():
    src = _text("mt5/NEXUS_MarketFeed/NEXUS_MarketFeed.mq5")
    assert "X-NEXUS-Admin-Token" in src
    assert "X-Admin-Mode: 1" in src
    assert "/api/v1/autotrade/admin/market-candles" in src
    assert "CopyRates" in src
