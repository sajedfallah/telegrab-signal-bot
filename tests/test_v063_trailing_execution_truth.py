from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAIL = (ROOT / "mt5/NEXUS_AutoTrade_UI65/Core/Include/TrailingEngine.mqh").read_text(encoding="utf-8")
TM = (ROOT / "mt5/NEXUS_AutoTrade_UI65/Core/Include/TradeManager.mqh").read_text(encoding="utf-8")
EA = (ROOT / "mt5/NEXUS_AutoTrade_UI65/Core/NEXUS_AutoTrade_Core.mq5").read_text(encoding="utf-8")
PROFILES = (ROOT / "app/autotrade/trailing_profiles.py").read_text(encoding="utf-8")


def test_partial_close_checks_trade_retcode_and_live_volume():
    assert "m_trade.ResultRetcode()" in TM
    assert "partial close not confirmed" in TM
    assert "expected_after" in TM
    assert "PositionClosePartial(ticket,close_volume)" in TM


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


def test_partial_profiles_use_configured_first_second_and_runner_shares():
    calc = TRAIL.split("double TargetClosePct", 1)[1].split("bool PartialRetryReady", 1)[0]
    assert 'NexusTrailGet(sig,"tp1_close_pct",30)' in calc
    assert 'NexusTrailGet(sig,"tp2_close_pct",30)' in calc
    assert 'NexusTrailGet(sig,"runner_pct",40)' in calc
    assert 'if(n>=count)return 100.0;' in calc


def test_impossible_minimum_lot_split_is_skipped_without_claiming_execution():
    plan = TRAIL.split("double ExecutablePartialVolume", 1)[1].split("bool PartialRetryReady", 1)[0]
    assert "max_partial=before-MathMax(minv,reserve)" in plan
    assert "if(max_partial+eps<minv)return 0;" in plan
    partials = TRAIL.split("void Partials", 1)[1].split("int Mode", 1)[0]
    assert 'NexusTrailSet(sig,field+"_skipped",1);' in partials
    assert "MathCeil(initv*runner_pct/100.0/step-1e-9)*step" in partials
    assert partials.index('NexusTrailSet(sig,field+"_skipped",1);') < partials.index("PartialCloseVolume(ticket,close_volume)")
    assert partials.index("PartialCloseVolume(ticket,close_volume)") < partials.rindex("CompleteTarget(ticket,sig,pt,entry,n,is_final_target);")
    assert 'NexusTrailSet(sig,field+"_done",1);' in TRAIL.split("void CompleteTarget", 1)[1].split("void Partials", 1)[0]


def test_restart_reconciles_pending_partial_with_broker_volume_before_retry():
    partials = TRAIL.split("void Partials", 1)[1].split("int Mode", 1)[0]
    assert 'NexusTrailGet(sig,field+"_pending_before",0)' in partials
    assert 'if(current<pending_before-threshold)' in partials
    assert partials.index('GlobalVariablesFlush();') < partials.index('PartialCloseVolume(ticket,close_volume)')
    assert partials.index('if(current<pending_before-threshold)') < partials.index('if(!PartialRetryReady(sig,n)) continue;')


def test_partial_recovers_identity_after_broker_clears_comment():
    assert "string NexusTrailSignalForTicket" in TRAIL
    assert 'string suffix=".ticket"' in TRAIL
    assert "sig=NexusTrailSignalForTicket(ticket,sig)" in TRAIL


def test_manual_partial_ladder_keeps_broker_final_tp_as_final_milestone():
    partials = TRAIL.split("void Partials", 1)[1].split("int Mode", 1)[0]
    assert 'int final_index=TargetCount(sig)+1;' in partials
    assert 'NexusTrailSet(sig,"tp"+IntegerToString(final_index),finaltp);' in partials
