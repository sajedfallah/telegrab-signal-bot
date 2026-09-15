from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINIAPP = ROOT / "miniapp"


def test_positions_v24_is_directly_activated_with_cache_bust_and_shared_import():
    admin = (MINIAPP / "admin.html").read_text(encoding="utf-8")
    typography = (MINIAPP / "vazirmatn.css").read_text(encoding="utf-8")
    assert '/miniapp/admin-positions-v24.css?v=20260915-positions1' in admin
    assert '/miniapp/vazirmatn.css?v=20260915-v24-positions1' in admin
    assert 'admin-positions-v24.css?v=20260915-positions1' in typography


def test_positions_v24_is_scoped_and_uses_signal_form_palette_tokens():
    css = (MINIAPP / "admin-positions-v24.css").read_text(encoding="utf-8")
    assert "#positions" in css
    assert "#14263c" in css
    assert "#17365f" in css
    assert "#24568b" in css
    assert "#c9d8e8" in css
    assert "linear-gradient(180deg,#ffffff 0%,#f7faff 100%)" in css


def test_positions_v24_forces_readable_primary_secondary_and_pnl_text():
    css = (MINIAPP / "admin-positions-v24.css").read_text(encoding="utf-8")
    assert ".card-head strong" in css
    assert ".admin-position-levels b" in css
    assert "b.profit" in css
    assert "b.loss" in css
    assert "opacity:1!important" in css


def test_positions_v24_styles_action_and_details_controls_without_js_changes():
    css = (MINIAPP / "admin-positions-v24.css").read_text(encoding="utf-8")
    js = (MINIAPP / "admin-position-compact-v7.js").read_text(encoding="utf-8")
    assert ".admin-position-more" in css
    assert ".admin-action-sheet>summary" in css
    assert ".trade-actions button.safe" in css
    assert ".trade-actions button.danger" in css
    assert "جزئیات پوزیشن" in js
