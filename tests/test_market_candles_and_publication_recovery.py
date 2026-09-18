from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.autotrade.publication_recovery_runtime import (
    _chart_job_overdue,
    _job_age_seconds,
    _publication_complete,
)
from app.market_candles import CandlePoint, CandleSeries, MarketFeedRequest, _tf


def _text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_market_timeframe_contract_is_exact_and_small():
    assert _tf("1m") == "M1"
    assert _tf("5m") == "M5"
    assert _tf("15m") == "M15"
    assert _tf("30m") == "M30"
    assert _tf("1h") == "H1"
    assert _tf("4h") == "H4"
    assert _tf("1D") == "D1"
    with pytest.raises(ValueError):
        _tf("H2")


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


def test_publication_completion_is_destination_aware_and_partial_both_is_incomplete():
    assert _publication_complete({"destination": "FREE", "free_message_id": 11, "vip_message_id": None})
    assert _publication_complete({"destination": "VIP", "free_message_id": None, "vip_message_id": 22})
    assert _publication_complete({"destination": "BOTH", "free_message_id": 11, "vip_message_id": 22})
    assert not _publication_complete({"destination": "BOTH", "free_message_id": 11, "vip_message_id": None})
    assert not _publication_complete({"destination": "BOTH", "free_message_id": None, "vip_message_id": 22})
    assert not _publication_complete({"destination": "BOTH", "free_message_id": None, "vip_message_id": None})


def test_chart_job_overdue_is_independent_from_chart_agent_polling():
    now = datetime(2026, 9, 14, 16, 30, tzinfo=timezone.utc)
    assert _chart_job_overdue({"status": "PENDING", "expires_at": (now - timedelta(seconds=1)).isoformat()}, now)
    assert _chart_job_overdue({"status": "CLAIMED", "expires_at": (now - timedelta(seconds=1)).isoformat()}, now)
    assert _chart_job_overdue({"status": "CAPTURING", "expires_at": (now - timedelta(seconds=1)).isoformat()}, now)
    assert not _chart_job_overdue({"status": "PENDING", "expires_at": (now + timedelta(seconds=1)).isoformat()}, now)
    assert not _chart_job_overdue({"status": "UPLOADED", "expires_at": (now - timedelta(seconds=1)).isoformat()}, now)


def test_chart_job_age_supports_fast_fallback_before_five_minute_ttl():
    now = datetime(2026, 9, 15, 6, 32, 40, tzinfo=timezone.utc)
    requested = (now - timedelta(seconds=21)).isoformat()
    assert _job_age_seconds({"requested_at": requested}, now) == pytest.approx(21.0)
    assert _job_age_seconds({"requested_at": ""}, now) is None


def test_publication_recovery_requires_broker_receipt_and_covers_recovery_gaps():
    src = _text("app/autotrade/publication_recovery_runtime.py")
    assert "_accepted_receipt(signal_id)" in src
    assert "allow_without_chart=True" in src
    assert "PUBLICATION_FALLBACK_QUEUED" in src
    assert "FAILED" in src and "EXPIRED" in src
    assert 'issuer_type == "MT5_ADMIN"' in src
    assert "CHART_JOB_RECOVERED" in src
    assert "CHART_JOB_EXPIRED_RECOVERY" in src
    assert "publication_chart_expired_signal_ids" in src
    assert "job expired without completed chart capture" in src
    assert "publication asset is missing" in src
    assert "COALESCE(free_message_id,0)=0 OR COALESCE(vip_message_id,0)=0" in src


def test_broker_confirmed_web_admin_signal_uses_canonical_marketfeed_without_chartagent_grace():
    src = _text("app/autotrade/publication_recovery_runtime.py")
    start = src.index('if issuer_type == "WEB_ADMIN"')
    end = src.index("job = db.get_signal_chart_capture_job", start)
    block = src[start:end]
    assert "_stage_broker_chart(row)" in block
    assert '"PUBLICATION_CANONICAL_VISUAL_QUEUED"' in block
    assert '"PUBLICATION_CANONICAL_VISUAL_WAIT"' in block
    assert '"MT5_MARKET_FEED_CANONICAL"' in block
    assert "allow_without_chart=True" in block
    assert "CHART_PLACEHOLDER" not in block
    assert "_PUBLICATION_CHART_GRACE_SECONDS" not in block


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
    assert "PERIOD_M30" in src
    assert "PERIOD_H4" in src
    assert "ENUM_TIMEFRAMES tfs[7]" in src


def test_marketfeed_v40_warms_new_timeframes_and_reports_sync_state():
    src = _text("mt5/NEXUS_MarketFeed/NEXUS_MarketFeed.mq5")
    assert '#property version   "1.20"' in src
    assert 'NEXUS-MARKET-FEED-1.2' in src
    assert 'WarmupSeries()' in src
    assert 'PERIOD_M30' in src and 'PERIOD_H4' in src
    assert 'SERIES_SYNCHRONIZED' in src
    assert 'CopyRates pending symbol=' in src
    assert 'history warmup pending symbol=' in src
    assert 'NEXUS MarketFeed V1.20 initialized tfs=M1,M5,M15,M30,H1,H4,D1' in src
