from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image

from app.autotrade.broker_chart_fallback import _render_chart


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def test_v26_broker_chart_renderer_outputs_valid_png_with_real_level_contract():
    signal = {
        "id": 54,
        "code": "NX-54",
        "symbol": "EURUSD",
        "timeframe": "M5",
        "direction": "SELL",
        "entry_price": 1.15411,
        "stop_loss": 1.15500,
    }
    candles = []
    base = 1.15350
    for idx in range(60):
        o = base + idx * 0.000003
        c = o + (0.00006 if idx % 3 else -0.00005)
        candles.append(
            {
                "time": 1_700_000_000 + idx * 300,
                "open": o,
                "high": max(o, c) + 0.00008,
                "low": min(o, c) - 0.00008,
                "close": c,
                "tick_volume": 100 + idx,
            }
        )
    meta = {
        "account": "80150619",
        "symbol": "EURUSD",
        "broker_symbol": "EURUSD.ec",
        "timeframe": "M5",
        "digits": 5,
        "age_seconds": 2.0,
    }
    raw = _render_chart(signal, candles, meta, [1.1530, 1.1520, 1.1510])
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(raw) > 10_000
    with Image.open(BytesIO(raw)) as image:
        assert image.format == "PNG"
        assert image.size == (1280, 720)


def test_v26_publication_recovery_prefers_fresh_mt5_marketfeed_before_placeholder():
    src = _text("app/autotrade/publication_recovery_runtime.py")
    assert "ensure_broker_chart_asset" in src
    assert '"fallback_mode": "MT5_MARKET_FEED" if broker_ok else "CHART_PLACEHOLDER"' in src
    assert "publication_broker_chart_signal_ids" in src
    assert "fresh MT5 MarketFeed chart staged after ChartAgent grace timeout" in src


def test_v26_broker_fallback_never_uses_external_or_synthetic_price_source():
    src = _text("app/autotrade/broker_chart_fallback.py")
    assert "mt5_market_candles" in src
    assert "account_number=? AND symbol=? AND timeframe=?" in src
    assert "_MAX_FEED_AGE_SECONDS = 90" in src
    assert "STALE_FEED" in src
    assert "NO_SERIES" in src
    assert "INSUFFICIENT_BARS" in src
    assert "requests" not in src
    assert "httpx" not in src
    assert "random" not in src


def test_v26_render_module_has_no_trade_execution_side_effects():
    src = _text("app/autotrade/broker_chart_fallback.py")
    forbidden = (
        "order_send",
        "send_order",
        "place_order",
        "MetaTrader5",
        "mt5.order",
        "autotrade_commands",
    )
    for marker in forbidden:
        assert marker not in src
