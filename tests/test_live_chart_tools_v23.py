from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MINIAPP = ROOT / "miniapp"


def test_v23_assets_are_activated_before_chart_modules():
    index = (MINIAPP / "index.html").read_text(encoding="utf-8")
    assert "live-chart-tools-v23.css?v=20260915-actionfix1" in index
    assert "live-chart-tools-v23.js?v=20260915-actionfix1" in index
    assert index.index("live-chart-tools-v23.js?v=20260915-actionfix1") < index.index("live-charts.js?v=20260914-livecharts-nav1")
    assert "live-chart-tools-v22.js?v=20260915-draw1" not in index


def test_v23_uses_chart_proxy_and_real_actions():
    js = (MINIAPP / "live-chart-tools-v23.js").read_text(encoding="utf-8")
    assert "new Proxy(chart" in js
    assert "coordinateToTime" in js
    assert "coordinateToPrice" in js
    assert "priceToCoordinate" in js
    for tool in ("horizontal", "trend", "rectangle", "fib", "risk"):
        assert f'data-v23-tool=\"{tool}\"' in js
    assert "data-v23-undo" in js
    assert "data-v23-clear" in js
    assert "data-v23-full" in js
    assert "data-v23-nexus" in js


def test_v23_does_not_own_market_feed_or_execution():
    js = (MINIAPP / "live-chart-tools-v23.js").read_text(encoding="utf-8")
    assert "WebSocket(" not in js
    assert "/market-candles" not in js
    assert "order_send" not in js
    assert "NEXUS Signal" not in js or "/signals?state=ACTIVE" in js
