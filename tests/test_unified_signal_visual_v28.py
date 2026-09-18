from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image
import pytest

from app.autotrade.broker_chart_fallback import (
    _render_chart,
    _signal_anchor,
    signal_visual_fingerprint,
)
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
        "order_type": "MARKET",
        "entry_price": 4278.0,
        "stop_loss": 4273.85,
        "risk_percent": 1.0,
        "rr_ratio": 3.0,
        "destination": "BOTH",
    }
    candles = []
    base = 4270.0
    for idx in range(90):
        o = base + idx * 0.11
        close = o + (0.55 if idx % 4 else -0.42)
        candles.append(
            {
                "time": 1_700_000_000 + idx * 300,
                "open": o,
                "high": max(o, close) + 0.35,
                "low": min(o, close) - 0.35,
                "close": close,
                "tick_volume": 100 + idx,
            }
        )
    meta = {
        "account": "80150619",
        "symbol": "XAUUSD",
        "broker_symbol": "XAUUSD.ec",
        "timeframe": "M5",
        "digits": 2,
        "captured_at": "2026-09-18T12:00:00+00:00",
        "age_seconds": 1.0,
    }
    return signal, candles, meta, [4282.5, 4284.0, 4287.0]


def test_v38_canonical_chart_is_valid_1600x900_png():
    signal, candles, meta, targets = _fixture_chart()
    raw = _render_chart(signal, candles, meta, targets)
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(raw) > 10_000
    with Image.open(BytesIO(raw)) as image:
        assert image.format == "PNG"
        assert image.size == (1600, 900)


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


def test_v39_visual_contract_is_minimal_chart_logo_and_levels_only():
    src = _text("app/autotrade/broker_chart_fallback.py")
    assert '_STYLE_VERSION = "nexus-signal-minimal-v6"' in src
    assert '"NEXUS SIGNAL"' not in src
    assert '"TRADE LEVELS"' not in src
    assert '"BROKER TRUTH' not in src
    assert "approved minimal NEXUS signal flash card" in src
    assert "logo only" in src
    assert "_ENTRY = (33, 150, 243)" in src
    assert "_TP = (28, 218, 126)" in src
    assert "_SL = (255, 82, 95)" in src
    assert 'level_specs.append(("ENTRY", entry, _ENTRY))' in src
    assert 'level_specs.append(("SL", sl, _SL))' in src
    assert 'level_specs.append((f"TP{idx}", float(value), _TP))' in src


def test_v37_fingerprint_changes_when_canonical_signal_numbers_change():
    signal, _, _, targets = _fixture_chart()
    first = signal_visual_fingerprint(signal, targets)
    second_signal = dict(signal)
    second_signal["entry_price"] = float(signal["entry_price"]) + 1.0
    second = signal_visual_fingerprint(second_signal, targets)
    assert first != second
    assert len(first) == 64
    assert len(second) == 64


def test_v37_visual_contract_never_fakes_broker_ohlc():
    src = _text("app/autotrade/broker_chart_fallback.py")
    forbidden = (
        'candle["close"] = entry',
        'candle["open"] = entry',
        'candle["high"] = entry',
        'candle["low"] = entry',
        "synthetic_entry",
        "random",
    )
    for marker in forbidden:
        assert marker not in src


def test_v37_publication_normalizer_preserves_final_render_dimensions():
    signal, candles, meta, targets = _fixture_chart()
    raw = _render_chart(signal, candles, meta, targets)
    normalized = _clean_publication_image(raw, {"entry": 4278.0, "tp1": 4282.5})
    with Image.open(BytesIO(normalized)) as image:
        assert image.size == (1600, 900)
    src = _text("app/autotrade/unified_signal_visual_runtime.py")
    assert '_STYLE_VERSION = "nexus-signal-minimal-v6"' in src


def test_v37_web_admin_uses_broker_renderer_as_sole_publication_authority():
    src = _text("app/autotrade/unified_signal_visual_runtime.py")
    assert 'if issuer == "WEB_ADMIN"' in src
    assert "ensure_broker_chart_asset(canonical)" in src
    assert '"MT5_MARKET_FEED_CANONICAL"' in src
    assert "VISUAL_GATE" in src
    assert "authoritative_mt5_screenshot" in src  # MT5_ADMIN compatibility only
    authority_fn = src[src.index("def _authoritative_staged_chart"):src.index("def _clean_publication_image")]
    assert 'issuer != "MT5_ADMIN"' in authority_fn


def test_v37_install_order_keeps_consistency_outermost():
    src = _text("app/combined_api.py")
    assert "install_unified_signal_visual(app)" in src
    assert "install_publication_consistency(app)" in src
    assert src.index("install_unified_signal_visual(app)") < src.index("install_publication_consistency(app)")


def test_v37_visual_code_does_not_touch_execution_or_generate_market_data():
    renderer = _text("app/autotrade/broker_chart_fallback.py")
    runtime = _text("app/autotrade/unified_signal_visual_runtime.py")
    combined = renderer + "\n" + runtime
    forbidden = (
        "order_send",
        "place_order",
        "send_order",
        "MetaTrader5",
        "requests.get",
        "httpx",
    )
    for marker in forbidden:
        assert marker not in combined


def test_v39_publication_normalizer_never_generates_blank_fallback():
    with pytest.raises(ValueError, match="missing"):
        _clean_publication_image(None, {})
    with pytest.raises(ValueError, match="invalid"):
        _clean_publication_image(b"not-a-png", {})


def test_v38_web_admin_publication_is_fingerprint_bound_and_chartagent_is_diagnostic_only():
    api = _text("app/autotrade/api.py")
    assert "expected_fingerprint = signal_visual_fingerprint(row, expected_targets)" in api
    assert "staged artwork does not match canonical signal fingerprint" in api
    assert 'if str(signal["issuer_type"] or "").upper() != "WEB_ADMIN":' in api
    assert '"DIAGNOSTIC_CHART_RECEIVED"' in api
