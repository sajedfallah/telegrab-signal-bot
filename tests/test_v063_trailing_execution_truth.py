from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAIL = (ROOT / "mt5/NEXUS_AutoTrade/Include/TrailingEngine.mqh").read_text(encoding="utf-8")
TM = (ROOT / "mt5/NEXUS_AutoTrade/Include/TradeManager.mqh").read_text(encoding="utf-8")
EA = (ROOT / "mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
PROFILES = (ROOT / "app/autotrade/trailing_profiles.py").read_text(encoding="utf-8")


def test_partial_close_checks_trade_retcode_and_live_volume():
    assert "m_trade.ResultRetcode()" in TM
    assert "partial close not confirmed" in TM
    assert "expected_after" in TM
    assert "PositionClosePartial(ticket,close_volume)" in TM


def test_trailing_recovers_signal_identity_when_broker_clears_comment():
    assert "NexusTrailRecoverSignal" in TRAIL
    assert 'NexusTrailRecoverSignal(ticket,PositionGetString(POSITION_COMMENT))' in TRAIL
    assert 'suffix=".ticket"' in TRAIL


def test_small_partial_uses_closest_valid_broker_volume_step():
    assert "double ceil_volume=MathCeil" in TM
    assert "double max_partial=" in TM
    assert "floor_valid" in TM and "ceil_valid" in TM


def test_full_close_requires_position_disappearance():
    assert "full close not confirmed" in TM
    assert "PositionSelectByTicket(ticket)" in TM


def test_sl_modification_is_execution_confirmed():
    assert "SL modify not confirmed" in TM
    assert "TRADE_RETCODE_NO_CHANGES" in TM


def test_tp_state_changes_only_after_confirmed_partial():
    assert "PartialCloseVolume(ticket,close_volume)" in TRAIL
    assert 'NexusTrailSet(sig,field+"_done",1);' in TRAIL
    assert "PartialRetrySchedule" in TRAIL
    assert "PartialRetryReset" in TRAIL


def test_partial_close_has_bounded_retry_backoff():
    assert 'MathPow(2.0' in TRAIL
    assert 'MathMin(30.0' in TRAIL
    assert '_next_retry' in TRAIL


def test_hybrid_runner_trailing_happens_after_target_management():
    assert "Partials(ticket,sig,pt,Price(symbol,pt),entry,risk);" in TRAIL
    assert "StructureTrail(ticket,sig,pt,symbol,runner_pr);" in TRAIL
    assert "ATRTrail(ticket,sig,pt,symbol,runner_pr);" in TRAIL


def test_all_seven_modes_remain_explicit():
    for i in range(1, 8):
        assert f"NEXUS_TRAIL_{i:02d}" in PROFILES
    assert "if(mode==1)" in TRAIL
    assert "else if(mode==2)" in TRAIL
    assert "else if(mode==3)" in TRAIL
    assert "else if(mode==4)" in TRAIL
    assert "else if(mode==5)" in TRAIL
    assert "else if(mode==6)" in TRAIL


def test_ea_release_is_v063():
    assert '#define NEXUS_EA_VERSION "0.6.5"' in EA
