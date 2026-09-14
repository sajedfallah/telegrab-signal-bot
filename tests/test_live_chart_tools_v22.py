from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINIAPP = ROOT / "miniapp"


def test_live_chart_tools_assets_are_activated():
    index = (MINIAPP / "index.html").read_text(encoding="utf-8")
    assert "live-chart-tools-v22.css?v=20260915-draw1" in index
    assert "live-chart-tools-v22.js?v=20260915-draw1" in index


def test_live_chart_tools_keep_existing_market_sources_untouched():
    js = (MINIAPP / "live-chart-tools-v22.js").read_text(encoding="utf-8")
    assert "LightweightCharts" in js
    assert "NexusLiveChartsForex" in js
    assert "NexusLiveCharts" in js
    assert "createChart" in js
    assert "fetchCandles" not in js
    assert "WebSocket(" not in js


def test_expected_drawing_tools_and_signal_overlay_exist():
    js = (MINIAPP / "live-chart-tools-v22.js").read_text(encoding="utf-8")
    for tool in ("horizontal", "trend", "rectangle", "fib", "risk"):
        assert f'data-chart-tool="{tool}"' in js
    assert "data-chart-nexus-overlay" in js
    assert "NEXUS Signal Overlay" in js
    assert "TP 2R" in js
    assert "nexus:chart-drawings:v22:" in js


def test_toolbar_is_scoped_to_live_chart_surface():
    css = (MINIAPP / "live-chart-tools-v22.css").read_text(encoding="utf-8")
    assert ".nexus-chart-tools-v22" in css
    assert ".nexus-chart-drawing-canvas" in css
    assert ".nexus-live-charts-page:fullscreen" in css
