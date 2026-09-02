from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EA=(ROOT/"mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
TR=(ROOT/"mt5/NEXUS_AutoTrade/Include/TrailingEngine.mqh").read_text(encoding="utf-8")
TYPES=(ROOT/"mt5/NEXUS_AutoTrade/Include/NexusTypes.mqh").read_text(encoding="utf-8")

def test_manual_trailing_is_explicit_opt_in():
    assert "InpManageManualTrades=false" in EA
    assert "input ENUM_NEXUS_TRAILING_PROFILE InpManualTrailingProfile=NEXUS_TRAIL_07;" in EA

def test_manual_trailing_uses_final_tp_and_initial_sl():
    assert 'NexusTrailSet(sig,"final_tp",tp)' in TR
    assert 'NexusTrailSet(sig,"initial_sl",sl)' in TR
    assert 'NexusTrailSet(sig,"initial_volume",v)' in TR

def test_manual_partial_targets_are_virtual_and_do_not_replace_final_tp():
    assert 'double finaltp=NexusTrailGet(sig,"final_tp",0)' in TR
    assert 'tp1=entry+d*risk' in TR
    assert 'tp2=entry+d*2*risk' in TR

def test_invalid_manual_sl_is_rejected():
    assert 'if(pt==POSITION_TYPE_BUY && sl>=e)return;' in TR
    assert 'if(pt==POSITION_TYPE_SELL && sl<=e)return;' in TR

def test_all_seven_profiles_are_supported():
    for i in range(1,8):
        assert f"NEXUS_TRAIL_{i:02d}" in TYPES


def test_manual_trailing_profile_is_enum_and_all_options_are_declared():
    assert "enum ENUM_NEXUS_TRAILING_PROFILE" in TYPES
    for i in range(1, 8):
        assert f"NEXUS_TRAIL_{i:02d} = {i}" in TYPES

def test_close_events_are_queued_until_position_is_gone():
    assert "QueuePendingClose(position_id,trans.deal)" in EA
    assert "ProcessPendingClosedTrades();" in EA
    assert "DEAL_ENTRY_INOUT" in EA

def test_mt5_trade_event_carries_stable_signal_id():
    api = (ROOT/"mt5/NEXUS_AutoTrade/Include/APIClient.mqh").read_text(encoding="utf-8")
    assert "const string signal_id" in api
    assert 'signal_id' in api and 'NexusJsonEscape(signal_id)' in api

def test_duplicate_signal_execution_has_idempotency_lock():
    assert "ClaimNexusSignal(s.signal_id)" in EA
    assert "ReleaseNexusSignalClaim(s.signal_id)" in EA


def test_break_even_waits_for_broker_stop_distance_and_verifies_actual_sl():
    assert 'MathMax(1,MathMax(stops,freeze))*point' in TR
    assert 'actual>=entry-point*0.1' in TR
    assert 'px-entry<dist' in TR


def test_trailing_is_throttled_to_one_update_per_second_per_position():
    assert 'trail_last_sec' in TR
