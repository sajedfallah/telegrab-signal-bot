from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def test_v37_is_installed_after_unified_visual_wrapper():
    src = _text("app/combined_api.py")
    assert "install_unified_signal_visual(app)" in src
    assert "install_publication_consistency(app)" in src
    assert src.index("install_unified_signal_visual(app)") < src.index("install_publication_consistency(app)")


def test_v37_serializes_publication_per_signal():
    src = _text("app/autotrade/publication_consistency_runtime.py")
    assert "_publish_locks: dict[int, asyncio.Lock]" in src
    assert "async with _lock_for(signal_id):" in src
    assert "consistency_short_circuit" in src


def test_v37_web_admin_restages_canonical_marketfeed_visual_not_chartagent_pixels():
    src = _text("app/autotrade/publication_consistency_runtime.py")
    assert "ensure_broker_chart_asset(signal)" in src
    assert '"source": "MT5_MARKET_FEED_CANONICAL"' in src
    assert "signal_visual_fingerprint" in src
    assert "MT5_CHART_AGENT" not in src
    assert 'job["image_path"]' not in src


def test_v37_does_not_touch_trading_execution_or_mt5_core():
    src = _text("app/autotrade/publication_consistency_runtime.py")
    forbidden = (
        "TradeManager",
        "TrailingEngine",
        "PARTIAL_CLOSE",
        "MOVE_SL_TO_ENTRY",
        "autotrade_trade_executions",
        "mt5_live_state",
    )
    for marker in forbidden:
        assert marker not in src
