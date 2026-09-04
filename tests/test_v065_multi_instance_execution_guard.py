from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EA = (
    ROOT / "mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5"
).read_text(encoding="utf-8")

TRAIL = (
    ROOT / "mt5/NEXUS_AutoTrade/Include/TrailingEngine.mqh"
).read_text(encoding="utf-8")

TM = (
    ROOT / "mt5/NEXUS_AutoTrade/Include/TradeManager.mqh"
).read_text(encoding="utf-8")


def test_busy_claim_is_not_reported_as_rejected():
    assert '"CLAIM BUSY"' in EA
    assert "NexusSignalExecutionDone" in EA
    assert (
        'SendSignalReceiptReliable(s.db_id,"rejected","",duplicate)'
        not in EA
    )
    assert '"DUPLICATE BLOCKED"' not in EA


def test_completed_claim_advances_without_false_rejection():
    assert '"ALREADY CLAIMED"' in EA
    assert "AdvanceSignalCursor(s.db_id);" in EA


def test_signal_cursor_refreshes_from_shared_terminal_state():
    assert 'GlobalVariableCheck(CursorKey("signal"))' in EA
    assert "shared_signal_cursor" in EA
    assert "shared_signal_cursor>g_last_signal_id" in EA


def test_command_cursor_refreshes_from_shared_terminal_state():
    assert 'GlobalVariableCheck(CursorKey("command"))' in EA
    assert "shared_command_cursor" in EA


def test_trailing_management_uses_atomic_global_claim():
    assert "NexusTrailClaimManageSecond" in TRAIL
    assert "GlobalVariableSetOnCondition" in TRAIL
    assert (
        'if(!NexusTrailClaimManageSecond(sig,now))'
        in TRAIL
    )


def test_new_positions_precreate_atomic_trailing_state():
    assert 'SaveDouble(s.signal_id,"trail_last_sec",0);' in TM


def test_manual_positions_precreate_atomic_trailing_state():
    assert 'NexusTrailSet(sig,"trail_last_sec",0);' in TRAIL
