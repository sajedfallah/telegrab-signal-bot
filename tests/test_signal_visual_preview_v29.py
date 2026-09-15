from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def test_v29_preview_tool_uses_canonical_renderer_without_mutating_signal_publication_state():
    src = _text("tools/send_signal_visual_preview_v29.py")
    assert "_load_series" in src
    assert "_render_chart" in src
    assert "MT5_MARKET_FEED" in src
    assert "production_signal_anchor_untouched" in src
    forbidden = (
        "ensure_broker_chart_asset",
        "save_mt5_signal_publication_asset",
        "clear_mt5_signal_publication_asset",
        "set_signal_publish_messages",
        "claim_signal_channel",
        "release_signal_channel_claim",
        "add_signal_event",
        "_publish_mt5_admin_signal_async",
        "publication_stage",
    )
    for marker in forbidden:
        assert marker not in src


def test_v29_preview_send_is_explicit_and_clearly_marked_test_only():
    src = _text("tools/send_signal_visual_preview_v29.py")
    assert 'parser.add_argument("--send"' in src or '"--send"' in src
    assert "if not args.send:" in src
    assert "NEXUS VISUAL PREVIEW" in src
    assert "TEST ONLY • NO TRADE ACTION" in src
    assert "send_photo" in src


def test_v29_preview_supports_only_free_or_vip_targets_from_existing_settings():
    src = _text("tools/send_signal_visual_preview_v29.py")
    assert 'choices=("VIP", "FREE")' in src
    assert "settings.vip_channel_id" in src
    assert "settings.free_channel_target" in src
    assert "BOT_TOKEN" not in src
    assert "VIP_CHANNEL_ID" not in src
