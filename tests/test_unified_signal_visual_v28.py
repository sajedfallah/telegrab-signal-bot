from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image

from app.autotrade.broker_chart_fallback import _render_chart, _signal_anchor
from app.autotrade.unified_signal_visual_runtime import _clean_publication_image


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def _fixture_chart() -> tuple[dict, list[dict[str, float]], dict, list[float]]:
    signal = {
        "id": 156,
        "code": "NX-156",
        "symbol": "XAUUSD",
        "timeframe": "M5",
        "direction": "BUY",
        "entry_price": 4278.0,
        "stop_loss": 4273.85,
    }
    candles = []
    base = 4270.0
    for idx in range(90):
        o = base + idx * 0.11
        c = o + (0.55 if idx % 4 else -0.42)
        candles.append(
            {
                "time": 1_700_000_000 + idx * 300,
                "open": o,
                "high": max(o, c) + 0.35,
                "low": min(o, c) - 0.35,
                "close": c,
                "tick_volume": 100 + idx,
            }
        )
    meta = {
        "account": "80150619",
        "symbol": "XAUUSD",
        "broker_symbol": "XAUUSD.ec",
        "timeframe": "M5",
        "digits": 2,
        "age_seconds": 1.0,
    }
    return signal, candles, meta, [4282.5, 4284.0, 4287.0]


def test_v28_approved_chart_is_clean_1280x720_png():
    signal, candles, meta, targets = _fixture_chart()
    raw = _render_chart(signal, candles, meta, targets)
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(raw) > 10_000
    with Image.open(BytesIO(raw)) as image:
        assert image.format == "PNG"
        assert image.size == (1280, 720)


def test_v30_signal_anchor_prefers_execution_time_and_floors_to_mt5_bar():
    signal = {
        "opened_at": "2026-09-15T17:32:56.542334+00:00",
        "limit_activated_at": "2026-09-15T17:31:00+00:00",
        "issued_at": "2026-09-15T17:30:00+00:00",
        "created_at": "2026-09-15T17:29:00+00:00",
    }
    bar_time, anchor_time, field = _signal_anchor(signal, "M5")
    expected_epoch = int(datetime(2026, 9, 15, 17, 32, 56, tzinfo=timezone.utc).timestamp())
    assert field == "opened_at"
    assert anchor_time.startswith("2026-09-15T17:32:56")
    assert bar_time == expected_epoch - (expected_epoch % 300)


def test_v30_visual_contract_uses_yellow_prices_and_entry_time_candle_window():
    src = _text("app/autotrade/broker_chart_fallback.py")
    assert '_STYLE_VERSION = "nexus-clean-signal-v3"' in src
    assert "_ENTRY = (33, 150, 243)" in src
    assert "_TP = (28, 218, 126)" in src
    assert "_SL = (255, 82, 95)" in src
    assert "_PRICE_TEXT = (255, 209, 102)" in src
    assert 'for field in ("opened_at", "limit_activated_at", "issued_at", "created_at")' in src
    assert "AND bar_time<=?" in src
    assert 'meta["reason"] = "ENTRY_ANCHOR_BAR_MISSING"' in src
    assert "line_start = min(width - 300, last_x +" in src
    assert "line_end = 1158" in src
    assert "dash=6, gap=5" in src
    assert 'level_specs.append(("ENTRY", entry, _ENTRY))' in src
    assert 'level_specs.append(("SL", sl, _SL))' in src
    assert 'level_specs.append((f"TP{idx}", float(value), _TP))' in src
    assert "label_font = _font(12, True)" in src
    assert "price_font = _font(11, False)" in src
    assert 'draw.text((price_x, label_y), f"{price:.{precision}f}"' in src
    assert "draw.rounded_rectangle" not in src


def test_v30_visual_contract_never_fakes_entry_by_mutating_broker_ohlc():
    src = _text("app/autotrade/broker_chart_fallback.py")
    forbidden = (
        'candle["close"] = entry',
        'candle["open"] = entry',
        'candle["high"] = entry',
        'candle["low"] = entry',
        "synthetic_entry",
    )
    for marker in forbidden:
        assert marker not in src


def test_v29_visual_contract_removes_old_decorative_chart_copy():
    src = _text("app/autotrade/broker_chart_fallback.py")
    forbidden = (
        "NEXUS  |  MT5 BROKER FEED",
        "Source: MT5 MarketFeed",
        "Freshness:",
        "CHART AUTHORITY",
        "VERIFIED CHART",
        "MARKET INTELLIGENCE",
    )
    for marker in forbidden:
        assert marker not in src


def test_v30_publication_normalizer_adds_no_extra_footer_or_trade_copy():
    signal, candles, meta, targets = _fixture_chart()
    raw = _render_chart(signal, candles, meta, targets)
    normalized = _clean_publication_image(raw, {"entry": 4278.0, "tp1": 4282.5})
    with Image.open(BytesIO(normalized)) as image:
        assert image.size == (1280, 720)
    src = _text("app/autotrade/unified_signal_visual_runtime.py")
    assert "old renderer added a header rail, large logo panel and a numeric footer" in src
    assert "without adding any extra text or panels" in src
    assert '_STYLE_VERSION = "nexus-clean-signal-v3"' in src


def test_v28_mt5_and_miniapp_share_one_renderer_before_publication():
    src = _text("app/autotrade/unified_signal_visual_runtime.py")
    assert '_SUPPORTED_ISSUERS = {"MT5_ADMIN", "WEB_ADMIN"}' in src
    assert "ensure_broker_chart_asset(canonical)" in src
    assert "card_generator.build_publication_signal_image = _clean_publication_image" in src
    assert "api_mod._publish_mt5_admin_signal_async = unified_publish" in src
    assert '"SIGNAL_VISUAL_CANONICALIZED"' in src
    assert '"style_version": _STYLE_VERSION' in src
    assert '"anchor_applied": broker_result.get("anchor_applied")' in src


def test_v28_install_order_is_after_existing_reliability_guards():
    src = _text("app/combined_api.py")
    assert "install_telegram_anchor_guard(app)" in src
    assert "install_unified_signal_visual(app)" in src
    assert src.index("install_telegram_anchor_guard(app)") < src.index("install_unified_signal_visual(app)")


def test_v28_does_not_touch_execution_or_generate_market_data():
    renderer = _text("app/autotrade/broker_chart_fallback.py")
    runtime = _text("app/autotrade/unified_signal_visual_runtime.py")
    combined = renderer + "\n" + runtime
    forbidden = (
        "order_send",
        "place_order",
        "send_order",
        "MetaTrader5",
        "random",
        "requests.get",
        "httpx",
    )
    for marker in forbidden:
        assert marker not in combined
