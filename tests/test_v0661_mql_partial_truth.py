from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHIM = (ROOT / "mt5/NEXUS_AutoTrade_UI65/NEXUS_AutoTrade.mq5").read_text(encoding="utf-8-sig")
PARTIAL = (
    ROOT / "mt5/NEXUS_AutoTrade_UI65/Core/Include/PartialLifecycleTruth.mqh"
).read_text(encoding="utf-8-sig")


def test_ui65_wraps_timer_and_trade_transaction_without_editing_core():
    assert "#define OnTimer            NEXUSCoreBase_OnTimer" in SHIM
    assert "#define OnTradeTransaction NEXUSCoreBase_OnTradeTransaction" in SHIM
    assert '#include "Core/NEXUS_AutoTrade_Core.mq5"' in SHIM
    assert '#include "Core/Include/PartialLifecycleTruth.mqh"' in SHIM
    assert "NEXUSCoreBase_OnTradeTransaction(trans,request,result);" in SHIM
    assert "NexusPartialTruthOnTradeTransaction(trans,request,result);" in SHIM


def test_partial_queue_is_processed_before_core_final_close_timer():
    partial_idx = SHIM.index("NexusPartialTruthProcessPending();")
    core_idx = SHIM.index("NEXUSCoreBase_OnTimer();")
    assert partial_idx < core_idx


def test_partial_truth_uses_exact_exit_deal_not_floating_position_pnl():
    assert "HistoryDealGetDouble(deal_ticket,DEAL_PROFIT)" in PARTIAL
    assert "HistoryDealGetDouble(deal_ticket,DEAL_SWAP)" in PARTIAL
    assert "HistoryDealGetDouble(deal_ticket,DEAL_COMMISSION)" in PARTIAL
    assert "HistoryDealGetDouble(deal_ticket,DEAL_FEE)" in PARTIAL
    assert "double stage_profit=gross_profit+swap+commission;" in PARTIAL
    assert "POSITION_PROFIT" not in PARTIAL


def test_partial_truth_sends_explicit_update_with_partial_reason_and_deal_identity():
    assert '"UPDATE",(string)position_ticket,signal_id,symbol,direction' in PARTIAL
    assert '"MARKET",0,"PARTIAL",event_time_ms' in PARTIAL
    assert "(string)position_id,(string)deal_ticket" in PARTIAL
    assert 'string event_id="PARTIAL-"+(string)position_id+"-"+(string)deal_ticket;' in PARTIAL


def test_partial_volume_is_the_broker_exit_deal_volume():
    assert "double closed_volume=HistoryDealGetDouble(deal_ticket,DEAL_VOLUME);" in PARTIAL
    assert "closed_volume,entry_price,sl,tp,exit_price,stage_profit" in PARTIAL


def test_only_still_open_exit_deals_are_queued_as_partials():
    assert "NexusPartialTruthPositionStillExists(position_id,position_ticket)" in PARTIAL
    assert "entry!=DEAL_ENTRY_OUT && entry!=DEAL_ENTRY_OUT_BY" in PARTIAL
    assert "DEAL_ENTRY_INOUT" not in PARTIAL


def test_retry_and_restart_recovery_are_present():
    assert "g_partial_truth_pending" in PARTIAL
    assert "NexusPartialTruthRecoverRecent();" in PARTIAL
    assert "next_try" in PARTIAL
    assert "MathPow(2.0" in PARTIAL
