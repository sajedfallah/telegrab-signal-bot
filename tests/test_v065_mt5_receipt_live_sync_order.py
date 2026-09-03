from pathlib import Path

p = Path("mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5")
src = p.read_text(encoding="utf-8")

def test_forced_live_sync_exists():
    assert "bool DoLiveSync(const bool force=false)" in src

def test_fresh_execution_syncs_before_receipt():
    start = src.index("CompleteNexusSignalClaim(s.signal_id);", src.index("if(!g_trade.OpenSignal"))
    end = src.index("AdvanceSignalCursor(s.db_id);", start)
    block = src[start:end]

    assert "DoLiveSync(true);" in block
    assert 'SendSignalReceiptReliable(s.db_id,receipt_status,(string)ticket,"");' in block
    assert block.index("DoLiveSync(true);") < block.index("SendSignalReceiptReliable")

def test_timer_refreshes_truth_before_receipt_retry():
    start = src.index("void OnTimer()")
    end = src.index("void OnTick()", start)
    block = src[start:end]

    assert "DoLiveSync();" in block
    assert "ProcessPendingReceipts();" in block
    assert block.index("DoLiveSync();") < block.index("ProcessPendingReceipts();")
