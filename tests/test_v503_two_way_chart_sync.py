from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MQ5=(ROOT/"mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
API=(ROOT/"app/autotrade/api.py").read_text(encoding="utf-8")
MAIN=(ROOT/"app/main.py").read_text(encoding="utf-8")

def test_existing_chart_is_used_for_screenshot():
    assert 'long chart_id=ChartOpen(symbol,InpTrailingTimeframe);' not in MQ5
    assert 'ChartFirst()' in MQ5 and 'ChartNext(cid)' in MQ5

def test_update_event_is_supported_end_to_end():
    assert 'OPEN|PENDING|UPDATE|CLOSE' in API
    assert 'event == "UPDATE"' in MAIN
    assert '_reply_signal_update' in MAIN

def test_trade_messages_are_copyable():
    assert 'protect_content=True' not in MAIN[MAIN.find('async def _publish_one_channel'):MAIN.find('async def _publish_signal')]

def test_license_edit_is_selected():
    assert 'OBJPROP_SELECTED,true' in MQ5
