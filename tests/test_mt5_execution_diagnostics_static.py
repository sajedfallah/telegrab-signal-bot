
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EA = (ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
TM = (ROOT / "mt5" / "NEXUS_AutoTrade" / "Include" / "TradeManager.mqh").read_text(encoding="utf-8")
API = (ROOT / "mt5" / "NEXUS_AutoTrade" / "Include" / "APIClient.mqh").read_text(encoding="utf-8")

def test_ea_version_and_visible_diagnostics():
    assert '#property version   "1.65"' in EA
    assert 'Trade state:' in EA
    assert 'Broker symbol:' in EA
    assert 'Reason:' in EA
    assert 'SetExecutionStatus("RECEIVED"' in EA
    assert 'SetExecutionStatus("ENTRY CHECK PASS"' in EA

def test_cursor_not_consumed_on_retryable_trade_failure():
    assert 'if(retryable)' in EA and 'break;' in EA
    failed_block = EA.split('if(!g_trade.OpenSignal', 1)[1].split('string receipt_status=', 1)[0]
    assert 'AdvanceSignalCursor(s.db_id);' in failed_block
    assert failed_block.index('if(retryable)') < failed_block.index('AdvanceSignalCursor(s.db_id);')

def test_trade_manager_exposes_retryability():
    assert 'bool LastFailureRetryable() const' in TM
    assert 'TRADE_RETCODE_CONNECTION' in TM
    assert 'TRADE_RETCODE_PRICE_OFF' in TM
    assert 'retcode=' in TM

def test_receipt_sends_error_to_backend():
    assert 'NexusJsonEscape(error_text)' in API
    assert 'Request("POST","/api/v1/autotrade/signal-receipt"' in API
    assert 'StringFormat("{\\"license_key\\"' in API
    assert 'error_text==""?"null"' in API


def test_status_panel_buttons_are_above_background_and_clickable():
    assert 'OBJPROP_ZORDER,100' in EA
    assert 'OBJPROP_BACK,false' in EA
    assert 'OBJPROP_SELECTABLE,false' in EA
