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


def test_tp_state_changes_only_after_confirmed_partial_or_explicit_milestone():
    assert "PartialCloseVolume(ticket,close_volume)" in TRAIL
    assert 'NexusTrailSet(sig,field+"_done",1);' in TRAIL
    assert "PartialRetrySchedule" in TRAIL
    assert "PartialRetryReset" in TRAIL
    assert 'NexusTrailSet(sig,field+"_milestone_only",1);' in TRAIL


def test_partial_close_has_bounded_retry_backoff():
    assert 'MathPow(2.0' in TRAIL
    assert 'MathMin(30.0' in TRAIL
    assert '_next_retry' in TRAIL


def test_hybrid_runner_trailing_happens_after_target_management_with_true_fallback():
    assert "Partials(ticket,sig,pt,px,entry,risk);" in TRAIL
    runner = TRAIL.split("void RunnerTrail", 1)[1].split("double Target", 1)[0]
    assert "if(!StructureTrail(ticket,sig,pt,symbol,pr))" in runner
    assert "ATRTrail(ticket,sig,pt,symbol,pr);" in runner
    mode5 = TRAIL.split("else if(mode==5)", 1)[1].split("else if(mode==6)", 1)[0]
    assert "RunnerTrail(ticket,sig,pt,symbol,runner_pr);" in mode5


def test_all_seven_modes_remain_explicit():
    for i in range(1, 8):
        assert f"NEXUS_TRAIL_{i:02d}" in PROFILES
    assert "if(mode==1)" in TRAIL
    assert "else if(mode==2)" in TRAIL
    assert "else if(mode==3)" in TRAIL
    assert "else if(mode==4)" in TRAIL
    assert "else if(mode==5)" in TRAIL
    assert "else if(mode==6)" in TRAIL


def test_ea_release_remains_protocol_compatible():
    assert '#define NEXUS_EA_VERSION "0.6.5"' in EA


def test_partial_profiles_use_configured_30_30_runner_contract_for_any_ladder():
    calc = TRAIL.split("double TargetClosePct", 1)[1].split("double ExecutablePartialVolume", 1)[0]
    assert 'NexusTrailGet(sig,"tp1_close_pct",30)' in calc
    assert 'NexusTrailGet(sig,"tp2_close_pct",30)' in calc
    assert 'NexusTrailGet(sig,"runner_pct",40)' in calc
    assert 'if(n>=count)return 100.0;' in calc
    assert 'if(n==1)return first;' in calc
    assert 'if(n==2 && count>=3)' in calc
    assert 'return 100.0/MathMax(1,count);' not in calc


def test_impossible_minimum_lot_split_completes_milestone_without_false_close():
    plan = TRAIL.split("double ExecutablePartialVolume", 1)[1].split("bool PartialRetryReady", 1)[0]
    assert "max_partial=before-MathMax(minv,reserve)" in plan
    assert "if(max_partial+eps<minv)return 0;" in plan
    partials = TRAIL.split("void Partials", 1)[1].split("int Mode", 1)[0]
    assert 'NexusTrailSet(sig,field+"_volume_skipped",1);' in partials
    assert 'NexusTrailSet(sig,field+"_closed_volume",0);' in partials
    assert "MathCeil(initv*runner_pct/100.0/step-1e-9)*step" in partials
    grid_skip = partials.index('NexusTrailSet(sig,field+"_volume_skipped",1);')
    milestone_complete = partials.index("CompleteTarget(ticket,sig,pt,entry,n,false);", grid_skip)
    partial_call = partials.index("PartialCloseVolume(ticket,close_volume)")
    assert grid_skip < milestone_complete < partial_call
    assert 'NexusTrailSet(sig,field+"_done",1);' in TRAIL.split("void CompleteTarget", 1)[1].split("void Partials", 1)[0]


def test_restart_reconciles_pending_partial_with_broker_volume_before_retry():
    partials = TRAIL.split("void Partials", 1)[1].split("int Mode", 1)[0]
    assert 'NexusTrailGet(sig,field+"_pending_before",0)' in partials
    assert 'if(current<pending_before-threshold)' in partials
    assert "SavePartialTruth(sig,n,initv,pending_before,current);" in partials
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


def test_step_trigger_is_be_and_lock_starts_after_first_full_step():
    step = TRAIL.split("void Step", 1)[1].split("void ATRTrail", 1)[0]
    assert "int levels=(int)MathFloor((pr-trigger)/step);" in step
    assert "if(levels<=0)return;" in step
    assert "MathFloor((pr-trigger)/step)+1" not in step


def test_actual_partial_volume_truth_is_persisted_for_diagnostics():
    truth = TRAIL.split("void SavePartialTruth", 1)[1].split("void CompleteTarget", 1)[0]
    assert '_closed_volume' in truth
    assert '_remaining_volume' in truth
    assert '_closed_pct_actual' in truth
    assert '_remaining_pct_actual' in truth


def test_management_ownership_is_per_broker_tick_not_one_second():
    assert "bool NexusTrailClaimManageTick" in TRAIL
    assert "tick.time_msc" in TRAIL
    manage = TRAIL.split("void ManageAll", 1)[1]
    assert "NexusTrailClaimManageTick(sig,tick_msc)" in manage
    assert "NexusTrailClaimManageSecond(sig,now)" not in manage
