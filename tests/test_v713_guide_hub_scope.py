from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def _ui():
    return (ROOT / "app" / "ui.py").read_text(encoding="utf-8")

def test_guide_hub_has_only_intro_and_expert_installation():
    ui = _ui()
    start = ui.index("def guide_hub_menu")
    end = ui.index("def guide_back_menu")
    segment = ui[start:end]
    assert "guide_intro" in segment
    assert "guide_mt5" in segment
    assert "guide_purchase" not in segment
    assert "guide_crypto" not in segment
    assert "guide_text" not in segment

def test_autotrade_menu_has_no_guide_entry_points():
    ui = _ui()
    start = ui.index("def autotrade_user_menu")
    end = ui.index("def exchange_selection_menu") if "def exchange_selection_menu" in ui else ui.index("def exchange_select")
    segment = ui[start:end]
    assert "autotrade_install_help" not in segment
    assert "autotrade_video_guide" not in segment
