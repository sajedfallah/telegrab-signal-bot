from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EA = (ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")


def test_tp_boxes_default_to_empty_not_literal_zero():
    # TP1..TP5 must default to "" so an unfilled box is distinguishable from
    # a real (invalid) 0 target. A literal "0" default made every signal with
    # fewer than 5 targets silently fail INVALID TP3/4/5 in IssueAdminSignal().
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
    # Every early-return validation branch inside IssueAdminSignal() must
    # Print() before calling SetPanel(), so a rejection is visible in the
    # Experts log regardless of which on-chart tab is active (SetPanel's
    # g_last_exec_reason only renders on the OVERVIEW tab).
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
        # A Print( call must appear in the same statement block, immediately
        # before the SetPanel(...) that carries this marker.
        preceding = body[max(0, idx - 220):idx]
        assert "Print(" in preceding, f"no Print() found before SetPanel(\"{marker}\")"
