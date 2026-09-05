from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "mt5/NEXUS_AutoTrade_UI65/NEXUS_AutoTrade_UI65.mq5").read_text(encoding="utf-8")
CORE = (ROOT / "mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
SHIM = (ROOT / "mt5/NEXUS_AutoTrade_UI65/NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")


def test_ui65_wraps_exact_hardened_core_instead_of_copying_trade_logic():
    assert '#include "NEXUS_AutoTrade.mq5"' in UI
    assert '#include "../NEXUS_AutoTrade/NEXUS_AutoTrade.mq5"' in SHIM
    assert '#define OnInit                 NEXUSCore_OnInit' in UI
    assert '#define OnTradeTransaction     NEXUSCore_OnTradeTransaction' in UI
    assert "g_trade.OpenSignal" not in UI
    assert "BuildReconcileItem" not in UI
    assert "ClaimNexusSignal" not in UI


def test_hardened_core_contract_remains_present():
    assert 'input string InpApiBaseUrl="https://api.nexustrade.ir";' in CORE
    assert "bool DoLiveSync(const bool force=false)" in CORE
    assert '"CLAIM BUSY"' in CORE
    assert '"ALREADY CLAIMED"' in CORE
    assert "shared_signal_cursor" in CORE
    assert "shared_command_cursor" in CORE
    assert "ReconcileIsoEventTime(event_time)" in CORE


def test_ui65_has_role_specific_three_level_workspace():
    assert 'string tab0=(g_access_mode==NEXUS_ADMIN?"NEW SIGNAL":"OVERVIEW");' in UI
    assert 'UI65Button("status_tab1","TRADES"' in UI
    assert 'UI65Button("status_tab2","SETTINGS"' in UI
    assert 'g_panel_tab=(g_access_mode==NEXUS_ADMIN?4:0);' in UI
    assert "g_panel_tab=6" in UI


def test_customer_setup_never_renders_admin_token_field():
    setup = UI[UI.index("void UI65ShowSetup"):UI.index("int UI65NexusPositions")]
    assert "if(InpAdminMode)" in setup
    assert 'UI65Label("admin_lbl","ADMIN TOKEN"' in setup
    assert 'UI65Label("license_lbl","LICENSE KEY"' in setup
    assert 'UI65HiddenEdit("admin","")' in setup
    assert "Admin credentials are never shown in customer mode." in setup


def test_setup_focus_guard_is_applied_only_after_production_core_include():
    include_at = SHIM.index('#include "../NEXUS_AutoTrade/NEXUS_AutoTrade.mq5"')
    delete_macro_at = SHIM.index("#define ObjectDelete")
    integer_macro_at = SHIM.index("#define ObjectSetInteger")
    string_macro_at = SHIM.index("#define ObjectSetString")
    assert include_at < delete_macro_at < integer_macro_at < string_macro_at
    assert "UI65IsFocusedEdit" in SHIM
    assert "UI65IsFocusedSetupEdit" in SHIM
    assert "property_id==OBJPROP_SELECTED && value==0" in SHIM
    assert "property_id==OBJPROP_TEXT && UI65IsFocusedEdit" in SHIM
    assert "if(current==value) return true;" in SHIM


def test_new_signal_requires_review_then_explicit_confirmation():
    assert 'UI65Button("sig_review","REVIEW SIGNAL"' in UI
    assert 'UI65Button("sig_issue",g_admin_signal_busy?"ISSUING...":"CONFIRM & ISSUE"' in UI
    assert 'if(sparam==UI65Name("sig_issue") && g_ui65_reviewing)' in UI
    assert "UI65CanReview" in UI


def test_destructive_trade_commands_require_confirmation():
    assert 'g_ui65_confirm_command="CLOSE_SIGNAL"' in UI
    assert 'g_ui65_confirm_command="CANCEL_PENDING"' in UI
    assert 'UI65Button("trade_confirm","CONFIRM"' in UI
    assert 'if(sparam==UI65Name("trade_confirm"))' in UI
    assert "IssueAdminCommand(command)" in UI


def test_ui_theme_is_dark_and_uses_segoe_without_second_minimize_button():
    assert 'OBJPROP_FONT,"Segoe UI"' in UI
    assert "OBJPROP_BGCOLOR,C'31,38,46'" in UI
    assert 'UI65Button("status_min"' in UI
    assert 'UI65Button("sig_min"' not in UI


def test_tick_path_only_delegates_to_hardened_core():
    block = UI[UI.index("void OnTick()"):UI.index("void OnTradeTransaction", UI.index("void OnTick()"))]
    executable = "\n".join(line for line in block.splitlines() if not line.strip().startswith("//"))
    assert "NEXUSCore_OnTick();" in executable
    assert "WebRequest" not in executable
    assert "ChartScreenShot" not in executable
    assert "UI65PaintStatusPanel" not in executable


def test_web_chart_agent_stays_separate_from_trading_ui_shell():
    assert "/api/v1/autotrade/admin/chart-capture/next" not in UI
    agent = (ROOT / "mt5/NEXUS_ChartAgent/NEXUS_ChartAgent.mq5").read_text(encoding="utf-8")
    assert "/api/v1/autotrade/admin/chart-capture/next" in agent
