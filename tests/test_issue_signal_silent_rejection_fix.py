from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EA = (ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")


def test_tp_boxes_default_to_empty_not_literal_zero():
    assert 'string v_tp1="0";' not in EA
    assert 'string v_tp2="0";' not in EA
    assert 'string v_tp3="0";' not in EA
    assert 'string v_tp4="0";' not in EA
    assert 'string v_tp5="0";' not in EA
    assert 'string v_tp1="";' in EA
    assert 'string v_tp2="";' in EA
    assert 'string v_tp3="";' in EA
    assert 'string v_tp4="";' in EA
    assert 'string v_tp5="";' in EA


def test_issue_admin_signal_rejections_are_printed_to_experts_log():
    start = EA.index("void IssueAdminSignal()")
    end = EA.index("void IssueAdminCommand(")
    body = EA[start:end]
    reject_panels = [
        "ISSUE SIGNAL ALREADY IN PROGRESS",
        "ADMIN AUTH REQUIRED",
        "TP ORDER INVALID: fill targets sequentially",
        "INVALID TP\"+(string)(i+1)",
        "INVALID SIGNAL INPUT",
        "MARKET PRICE UNAVAILABLE",
        "INVALID ENTRY",
        "SELECT CHANNEL ACCESS",
        "TP ORDER INVALID\"",
        "BUY TP GEOMETRY INVALID",
        "SELL TP GEOMETRY INVALID",
    ]
    for marker in reject_panels:
        idx = body.index(marker)
        preceding = body[max(0, idx - 220):idx]
        assert "Print(" in preceding, f"no Print() found before SetPanel(\"{marker}\")"


def test_issue_signal_button_is_restored_after_all_terminal_paths():
    start = EA.index("void IssueAdminSignal()")
    end = EA.index("void IssueAdminCommand(")
    body = EA[start:end]
    helper_start = EA.index("void FinishAdminSignalIssue()")
    helper_end = EA.index("void IssueAdminSignal()", helper_start)
    helper = EA[helper_start:helper_end]

    assert 'OBJPROP_TEXT,"ISSUE SIGNAL"' in helper
    assert 'g_admin_signal_busy=false;' in helper
    assert 'g_admin_signal_busy=false;' not in body
    assert body.count('FinishAdminSignalIssue();') >= 10
    assert 'FinishAdminSignalIssue();\n   SetPanel(g_last_exec_state=="EXECUTED"' in body
