from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image
import pytest

from app.autotrade.broker_chart_fallback import (
    _price_viewport,
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


def test_v43_visual_contract_is_minimal_chart_logo_and_levels_only():
    src = _text("app/autotrade/broker_chart_fallback.py")
    assert '_STYLE_VERSION = "nexus-signal-minimal-v7"' in src
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
    assert '_STYLE_VERSION = "nexus-signal-minimal-v7"' in src


def test_v45_authority_signals_use_text_only_publication_wrapper():
    src = _text("app/autotrade/unified_signal_visual_runtime.py")
    install = src[src.index("def install_unified_signal_visual"):]
    assert '"TEXT_ONLY"' in install
    assert "ensure_broker_chart_asset(canonical)" not in install
    assert "VISUAL_GATE" not in install
    assert "chart_base64" in install  # accepted for compatibility
    assert "None," in install  # legacy image input is deliberately discarded


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


def test_v43_publication_normalizer_never_generates_blank_fallback():
    with pytest.raises(ValueError, match="missing"):
        _clean_publication_image(None, {})
    with pytest.raises(ValueError, match="invalid"):
        _clean_publication_image(b"not-a-png", {})


def test_v45_signal_publisher_has_no_image_or_visual_gate():
    api = _text("app/autotrade/api.py")
    start = api.index("async def _publish_mt5_admin_signal_async")
    end = api.index("def _publish_mt5_admin_signal(", start)
    publisher = api[start:end]
    assert "send_message(" in publisher
    assert "send_photo(" not in publisher
    assert "build_publication_signal_image" not in publisher
    assert "signal_visual_fingerprint" not in publisher
    assert "VISUAL_GATE" not in publisher
    assert '"publication_mode": "TEXT_ONLY"' in publisher


def test_v43_distant_levels_do_not_flatten_broker_candles():
    _, candles, _, _ = _fixture_chart()
    visible = candles[-72:]
    candle_low = min(float(item["low"]) for item in visible)
    candle_high = max(float(item["high"]) for item in visible)
    candle_span = candle_high - candle_low

    # Deliberately extreme TP/SL values reproduce the production failure mode
    # where one distant level used to flatten every candle into a thin band.
    y_min, y_max = _price_viewport(visible, [4278.0, 4300.0, 4200.0])
    viewport_span = y_max - y_min

    assert viewport_span > candle_span
    assert candle_span / viewport_span >= 0.30


def test_v43_label_resolver_uses_live_chart_bounds_not_legacy_690px_limit():
    src = _text("app/autotrade/broker_chart_fallback.py")
    assert "top_bound=chart_top + 20" in src
    assert "bottom_bound=chart_bottom - 20" in src
    assert "bottom_bound = 690" not in src
    assert "_VISIBLE_BARS = 72" in src


def test_v44_fingerprint_is_bound_to_renderer_style_version():
    src = _text("app/autotrade/broker_chart_fallback.py")
    assert '"style_version": _STYLE_VERSION' in src
    assert '_STYLE_VERSION = "nexus-signal-minimal-v7"' in src


def test_v45_mt5_issue_does_not_stage_signal_screenshot():
    api = _text("app/autotrade/api.py")
    start = api.index('async def issue_mt5_admin_signal(')
    end = api.index('@app.post("/api/v1/admin/mt5/signals/{signal_id}/command")', start)
    block = api[start:end]
    assert "save_mt5_signal_publication_asset" not in block
    assert "pending_signal_charts" not in block
    assert "legacy chart_base64 is accepted" in block


def test_v45_mt5_core_does_not_capture_signal_screenshot():
    src = _text("mt5/NEXUS_AutoTrade_UI65/Core/NEXUS_AutoTrade_Core.mq5")
    anchor = src.index("NEXUS ADMIN SIGNAL: submit start")
    block = src[max(0, anchor - 700):anchor + 1200]
    assert 'CaptureChartBase64(symbol,"SIGNAL")' not in block
    assert "publication=TEXT_ONLY" in block


def test_v45_legacy_channel_root_is_text_only():
    src = _text("app/main.py")
    start = src.index("async def _publish_one_channel")
    end = src.index("async def _publish_signal", start)
    block = src[start:end]
    assert "send_message(" in block
    assert "send_photo(" not in block


def test_v45_miniapp_signal_creation_does_not_create_chart_capture_job():
    base = _text("app/miniapp_admin_api.py")
    start = base.index("def create_signal(")
    end = base.index('@router.get("/signals")', start)
    block = base[start:end]
    assert "create_chart_capture_job" not in block
    assert "WAITING_EXECUTION" in block

    runtime = _text("app/autotrade/miniapp_execution_runtime.py")
    start = runtime.index("def create_miniapp_signal(")
    end = runtime.index('_replace_route(app, "/miniapp/api/admin/signals"', start)
    block = runtime[start:end]
    assert "create_chart_capture_job" not in block
    assert "WAITING_EXECUTION" in block


def test_v46_legacy_bot_signal_flow_has_no_chart_upload_step():
    src = _text("app/main.py")
    start = src.index('@router.callback_query(F.data.startswith("sigmarket:"))')
    end = src.index("async def _show_signal_direction", start)
    block = src[start:end]
    assert "Flow.signal_chart" not in block
    assert "Chart Image" not in block
    assert "تصویر چارت" not in block
    assert "signal_chart_file_id=None" in block


def test_v46_current_mt5_signal_client_sends_no_chart_payload():
    src = _text("mt5/NEXUS_AutoTrade_UI65/Core/Include/APIClient.mqh")
    start = src.index("bool IssueAdminSignal(")
    end = src.index("bool IssueAdminCommand(", start)
    block = src[start:end]
    assert "chart_base64" not in block
    assert "TEXT_ONLY" in block
