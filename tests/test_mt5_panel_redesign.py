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


def test_ui_port_does_not_absorb_web_screenshot_agent_into_trading_ea():
    # Web screenshot work is intentionally isolated in NEXUS_ChartAgent.ex5.
    # The trading EA keeps its existing native MT5-admin signal screenshot path,
    # but must not poll the Web chart-capture job endpoints.
    assert "/api/v1/autotrade/admin/chart-capture/next" not in EA
    agent = (Path(__file__).resolve().parents[1] / "mt5/NEXUS_ChartAgent/NEXUS_ChartAgent.mq5").read_text(encoding="utf-8")
    assert "/api/v1/autotrade/admin/chart-capture/next" in agent
    assert "void OnTick()" in agent
