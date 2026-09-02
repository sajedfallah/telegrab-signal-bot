from pathlib import Path
from datetime import datetime, timezone
from app import db

ROOT=Path(__file__).resolve().parents[1]

def test_signal_schema_and_payload_support_order_type_and_abs_deviation(tmp_path):
    old=db.DB_PATH
    db.DB_PATH=tmp_path/'v704.db'
    try:
        db.init_db()
        row=db.create_signal(
            market_type='FOREX',symbol='XAUUSD',direction='BUY',entry_price=4471,stop_loss=4460,
            targets=[4480],risk_percent=1,rr_ratio=1,destination='VIP',chart_file_id=None,created_by=1,
            trailing_code='NEXUS_TRAIL_04',trailing_name='Market Structure',order_type='LIMIT',
            max_entry_deviation_abs=5.0,volume_mode='RISK'
        )
        assert row['order_type']=='LIMIT'
        assert float(row['max_entry_deviation_abs'])==5.0
    finally:
        db.DB_PATH=old

def test_report_dispatch_claim_is_atomic(tmp_path):
    old=db.DB_PATH
    db.DB_PATH=tmp_path/'reports.db'
    try:
        db.init_db()
        assert db.claim_report_dispatch('daily','2026-08-19',123,'a','b') is True
        assert db.claim_report_dispatch('daily','2026-08-19',123,'a','b') is False
        db.release_report_dispatch('daily','2026-08-19',123)
        assert db.claim_report_dispatch('daily','2026-08-19',123,'a','b') is True
    finally:
        db.DB_PATH=old

def test_signal_creation_flow_has_market_and_limit_choice():
    main=(ROOT/'app/main.py').read_text(encoding='utf-8')
    ui=(ROOT/'app/ui.py').read_text(encoding='utf-8')
    assert 'sigorder:MARKET' in ui
    assert 'await state.update_data(signal_order_type=order_type)' in main
    assert 'order_type=str(data.get("signal_order_type") or "MARKET")' in main

def test_mt5_limit_and_absolute_deviation_support_present():
    tm=(ROOT/'mt5/NEXUS_AutoTrade/Include/TradeManager.mqh').read_text(encoding='utf-8')
    parser=(ROOT/'mt5/NEXUS_AutoTrade/Include/SignalParser.mqh').read_text(encoding='utf-8')
    ea=(ROOT/'mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5').read_text(encoding='utf-8')
    assert 'ORDER_TYPE_BUY_LIMIT' in tm and 'ORDER_TYPE_SELL_LIMIT' in tm
    assert 'TRADE_ACTION_PENDING' in tm and 'OrderSend(req,res)' in tm
    assert 'max_entry_deviation_abs' in tm
    assert 'order_type' in parser
    assert 'NotifyLimitActivations' in ea
    assert '"pending"' in ea and '"activated"' in ea

def test_scheduled_reports_use_strict_clock_and_atomic_claim():
    main=(ROOT/'app/main.py').read_text(encoding='utf-8')
    assert 'now.hour==daily_h and now.minute==daily_m' in main
    assert 'now.weekday()==weekly_day and now.hour==weekly_h and now.minute==weekly_m' in main
    assert 'claim_report_dispatch' in main
