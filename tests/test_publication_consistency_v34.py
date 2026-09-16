from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def test_v34_is_installed_after_unified_visual_wrapper():
    src = _text("app/combined_api.py")
    assert "install_unified_signal_visual(app)" in src
    assert "install_publication_consistency(app)" in src
    assert src.index("install_unified_signal_visual(app)") < src.index("install_publication_consistency(app)")


def test_v34_serializes_publication_per_signal():
    src = _text("app/autotrade/publication_consistency_runtime.py")
    assert "_publish_locks: dict[int, asyncio.Lock]" in src
    assert "async with _lock_for(signal_id):" in src
    assert "consistency_short_circuit" in src


def test_v34_real_chart_job_restages_authoritative_asset():
    src = _text("app/autotrade/publication_consistency_runtime.py")
    assert '_READY_CHART = {"UPLOADED", "COMPLETED"}' in src
    assert 'job["image_path"]' in src
    assert "db.save_mt5_signal_publication_asset(signal_id, path)" in src
    assert "publication_stage='CHART_RECEIVED'" in src
    assert '"source": "MT5_CHART_AGENT"' in src


def test_v34_does_not_touch_trading_execution_or_mt5_core():
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
