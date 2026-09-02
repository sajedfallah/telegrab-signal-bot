from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_subscription_plan_button_contains_price_once():
    text = (ROOT / "app" / "ui.py").read_text(encoding="utf-8")
    assert 'f"{service_label} | {duration} | {raw_price} USDT"' in text
    assert text.count('def plans_for_service') == 1


def test_signal_payload_and_caption_have_timeframe_and_order_type():
    service = (ROOT / "app" / "autotrade" / "service.py").read_text(encoding="utf-8")
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert '"timeframe": str(row["timeframe"]' in service
    assert "type_labels = {" in main
    assert "BUY_STOP" in main and "SELL_STOP" in main
    assert 'Timeframe: <b>' in main


def test_limit_activation_is_idempotent():
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert 'if existing["limit_activated_at"]:' in main
    assert 'db.mark_limit_activated(int(existing["id"]))' in main


def test_mt5_limit_engine_checks_broker_distance_and_expiration():
    tm = (ROOT / "mt5" / "NEXUS_AutoTrade" / "Include" / "TradeManager.mqh").read_text(encoding="utf-8")
    ea = (ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
    for token in ["SYMBOL_TRADE_STOPS_LEVEL", "SYMBOL_TRADE_FREEZE_LEVEL", "SYMBOL_EXPIRATION_MODE", "ORDER_TIME_SPECIFIED", "ValidateLimitGeometry"]:
        assert token in tm
    assert "InpLimitExpirationHours" in ea
    assert "InpStrictLimitBrokerChecks" in ea


def test_mt5_open_event_id_is_deterministic():
    ea = (ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
    assert 'event_id=event_name+"-"+(string)position_id+"-"+(string)deal_ticket;' in ea
    assert "GetTickCount64()" not in ea[ea.find('bool SendManualOrClosedTradeEvent'):ea.find('bool SendManualOrClosedTradeEvent')+2500]


def test_minimized_status_panel_removes_manual_destination_controls():
    ea = (ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
    block = ea[ea.index('if(g_panel_minimized)'):ea.index('string tabs[6]')]
    assert 'DeleteManualDestinationPanel();' in block
    assert 'DeleteStatusTabs();' in block


def test_mt5_package_contains_source_only():
    mt5 = ROOT / "mt5" / "NEXUS_AutoTrade"
    files = sorted(p.name for p in mt5.iterdir())
    assert files == ["Include", "NEXUS_AutoTrade.mq5", "NEXUS_Reset_Runtime.mq5"]
    assert not (mt5 / "NEXUS_AutoTrade.ex5").exists()
