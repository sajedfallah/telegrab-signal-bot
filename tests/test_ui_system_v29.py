from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def test_v29_design_system_is_loaded_after_existing_polish_layers():
    css = _text("miniapp/vazirmatn.css")
    assert '@import url("./ui-system-v29.css?v=20260915-minimal1")' in css
    assert css.index("ui-polish-v16.css") < css.index("ui-system-v29.css")
    assert css.index("admin-positions-v24.css") < css.index("ui-system-v29.css")


def test_v29_uses_flat_limited_palette_and_spacing_tokens():
    css = _text("miniapp/ui-system-v29.css")
    for marker in (
        "--ui-bg: #07111d",
        "--ui-surface: #0d1723",
        "--ui-text: #edf3f8",
        "--ui-muted: #8fa0b2",
        "--ui-accent: #27cdb9",
        "--ui-space-3: 12px",
        "--ui-space-4: 16px",
        "background-image: none !important",
    ):
        assert marker in css


def test_v29_price_numbers_are_small_light_and_unboxed():
    css = _text("miniapp/ui-system-v29.css")
    assert ".app-shell .price-v2-price b" in css
    assert ".app-shell .order-v2-total b" in css
    assert "font-size: 11px !important" in css
    assert "font-weight: 400 !important" in css
    assert "background: transparent !important" in css
    assert "border: 0 !important" in css
    assert "color: var(--ui-muted) !important" in css
    assert "font-variant-numeric: tabular-nums" in css


def test_v29_buttons_icons_and_interactions_are_consistent():
    css = _text("miniapp/ui-system-v29.css")
    assert "--ui-radius: 12px" in css
    assert "stroke-width: 1.75 !important" in css
    assert "button:hover" in css
    assert "button:active" in css
    assert "button:focus-visible" in css
    assert "transform: translateY(1px) scale(.99)" in css
