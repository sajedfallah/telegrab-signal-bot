from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.autotrade import chart_capture_queue_guard
from app.autotrade import chart_delivery_guard
from app.autotrade.unified_signal_visual_runtime import _authoritative_staged_chart


ROOT = Path(__file__).resolve().parents[1]


def _fake_png(path: Path) -> None:
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + (b"NEXUS" * 120))


def test_v33_web_admin_chart_received_preserves_real_chartagent_asset(monkeypatch, tmp_path):
    image = tmp_path / "nx-real.png"
    _fake_png(image)
    monkeypatch.setattr(
        "app.autotrade.unified_signal_visual_runtime.db.get_mt5_signal_publication_asset",
        lambda signal_id: str(image),
    )
    row = {
        "id": 64,
        "issuer_type": "WEB_ADMIN",
        "publication_stage": "CHART_RECEIVED",
    }
    assert _authoritative_staged_chart(row) == str(image)


def test_v33_web_admin_fallback_asset_is_not_mistaken_for_chartagent(monkeypatch, tmp_path):
    image = tmp_path / "nx-fallback.png"
    _fake_png(image)
    monkeypatch.setattr(
        "app.autotrade.unified_signal_visual_runtime.db.get_mt5_signal_publication_asset",
        lambda signal_id: str(image),
    )
    row = {
        "id": 64,
        "issuer_type": "WEB_ADMIN",
        "publication_stage": "PUBLISHED_REPAIR_PENDING",
    }
    assert _authoritative_staged_chart(row) is None


def test_v33_mt5_admin_source_asset_remains_authoritative(monkeypatch, tmp_path):
    image = tmp_path / "mt5-source.png"
    _fake_png(image)
    monkeypatch.setattr(
        "app.autotrade.unified_signal_visual_runtime.db.get_mt5_signal_publication_asset",
        lambda signal_id: str(image),
    )
    row = {
        "id": 70,
        "issuer_type": "MT5_ADMIN",
        "publication_stage": "WAITING_EXECUTION",
    }
    assert _authoritative_staged_chart(row) == str(image)


def test_v33_terminal_repair_queue_excludes_closed_signals(monkeypatch):
    candidates = [{"signal_id": 41}, {"signal_id": 72}]
    monkeypatch.setattr(chart_delivery_guard, "_terminal_repair_candidates", lambda account: list(candidates))
    monkeypatch.setattr(
        chart_capture_queue_guard.db,
        "get_signal",
        lambda signal_id: {"status": "CLOSED"} if int(signal_id) == 41 else {"status": "ACTIVE"},
    )
    app = SimpleNamespace(state=SimpleNamespace())
    chart_capture_queue_guard.install_chart_capture_queue_guard(app)
    assert chart_delivery_guard._terminal_repair_candidates("80150619") == [{"signal_id": 72}]


def test_v33_install_order_and_visual_contract_are_explicit():
    combined = (ROOT / "app" / "combined_api.py").read_text(encoding="utf-8-sig")
    visual = (ROOT / "app" / "autotrade" / "unified_signal_visual_runtime.py").read_text(encoding="utf-8-sig")
    assert "install_chart_delivery_guard(app)" in combined
    assert "install_chart_capture_queue_guard(app)" in combined
    assert "install_chart_repair_claim_runtime(app)" in combined
    assert combined.index("install_chart_delivery_guard(app)") < combined.index("install_chart_capture_queue_guard(app)")
    assert combined.index("install_chart_capture_queue_guard(app)") < combined.index("install_chart_repair_claim_runtime(app)")
    assert 'visual_source = "MT5_CHART_AGENT" if issuer == "WEB_ADMIN" else "MT5_SOURCE_SCREENSHOT"' in visual
    assert 'visual_source = "MT5_MARKET_FEED_FALLBACK"' in visual
    assert "authoritative_mt5_screenshot" in visual
