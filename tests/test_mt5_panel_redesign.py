from pathlib import Path


EA = (Path(__file__).resolve().parents[1] / "mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")


def test_admin_workspace_has_separate_signal_trade_and_settings_tabs():
    assert 'string main_tabs[3]={"NEW SIGNAL","TRADES","SETTINGS"};' in EA
    assert "void PaintAdminTradePanel()" in EA
    assert "g_panel_tab==6" in EA


def test_signal_workspace_has_one_global_minimize_control():
    block = EA[EA.index("void PaintAdminSignalPanel()"):EA.index("string CanonicalSignalSymbol")]
    assert 'UISetButton("sig_min"' not in block
    assert 'UISetButton("status_min"' in EA


def test_customer_setup_does_not_render_admin_token():
    setup = EA[EA.index("void ShowSetupPanel"):EA.index("void ReadSetupFields")]
    assert "if(InpAdminMode)" in setup
    assert 'UISetLabel("admin_lbl"' in setup
    assert 'UISetLabel("license_lbl"' in setup
    assert setup.index("if(InpAdminMode)") < setup.index('UISetLabel("admin_lbl"') < setup.index("else")


def test_primary_issue_action_is_not_clipped():
    assert 'UISetButton("sig_issue",g_admin_signal_busy?"ISSUING...":"ISSUE SIGNAL",24,536,460,34' in EA


def test_theme_uses_shared_readable_font_and_dark_inputs():
    assert 'OBJPROP_FONT,"Segoe UI"' in EA
    assert "OBJPROP_BGCOLOR,C'31,38,46'" in EA
