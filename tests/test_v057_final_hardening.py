
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_pricing_catalog():
    # Avoid importing Settings because deployment environment variables are intentionally absent in unit tests.
    text = (ROOT / "app" / "config.py").read_text(encoding="utf-8")
    assert '"VIP12M"' in text and '"usdt":"239"' in text
    assert '"AEX1M"' in text and '"usdt":"5"' in text
    assert '"AEX12M"' in text and '"usdt":"49"' in text
    assert '"AUTO1M"' in text and '"usdt":"30"' in text
    assert '"AUTO3M"' in text and '"usdt":"83"' in text
    assert '"AUTO6M"' in text and '"usdt":"155"' in text
    assert '"AUTO12M"' in text and '"usdt":"289"' in text


def test_subscription_buttons_are_compact_and_unique():
    text = (ROOT / "app" / "ui.py").read_text(encoding="utf-8")
    assert '"VIP", "buyservice:VIP"' in text
    assert '"AutoTrade", "buyservice:AUTO"' in text
    assert '"VIP + AutoTrade", "buyservice:BUNDLE"' in text
    assert "— {vip_status}" not in text
    assert "AutoTrade Expert — {auto_status}" not in text


def test_api_rejects_missing_license_in_ea_resolver():
    text = (ROOT / "app" / "autotrade" / "api.py").read_text(encoding="utf-8")
    assert 'raise AutoTradeError("Auto Trade license is required")' in text
    assert 'return authorize_standa' not in text[text.find('def _resolve_ea_auth'):text.find('@app.get("/api/v1/autotrade/health")')]


def test_service_rejects_missing_license_in_ea_resolver():
    text = (ROOT / "app" / "autotrade" / "service.py").read_text(encoding="utf-8")
    start = text.find("def _resolve_service_ea_auth")
    end = text.find("def active_signals", start)
    block = text[start:end]
    assert 'raise AutoTradeError("Auto Trade license is required")' in block
    assert "authorize_standard_mt5" not in block


def test_pending_trade_event_contract_exists():
    api = (ROOT / "app" / "autotrade" / "api.py").read_text(encoding="utf-8")
    db = (ROOT / "app" / "db.py").read_text(encoding="utf-8")
    assert 'pattern="OPEN|PENDING|UPDATE|CLOSE"' in api
    event_block = api[api.index('event = req.event.upper()'):api.index('if event in {"OPEN", "PENDING"}', api.index('event = req.event.upper()'))]
    assert 'if event not in {"OPEN", "PENDING", "UPDATE", "CLOSE"}' in event_block
    assert 'if event_name not in {"OPEN", "PENDING", "UPDATE", "CLOSE"}:' in db
    assert '"order_type": str(req.order_type or "MARKET").upper()' in api


def test_mt5_manual_limit_bridge_and_admin_token():
    mq = (ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
    api = (ROOT / "mt5" / "NEXUS_AutoTrade" / "Include" / "APIClient.mqh").read_text(encoding="utf-8")
    assert 'return InpAdminMode || StringLen(EffectiveAdminToken())>0;' in mq
    assert "TRADE_TRANSACTION_ORDER_ADD" in mq
    assert 'TradeEvent("PENDING"' in mq
    assert 'QueuePendingOpen(position_id,trans.deal,open_destination,pending_signal)' in mq
    assert 'order_type\\":\\"%s\\"' in api


def test_tabbed_status_panel_exists():
    mq = (ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
    for tab in ["OVERVIEW", "CONNECTION", "TRADING", "RISK", "SIGNAL", "SYSTEM"]:
        assert tab in mq
    assert "g_panel_minimized" in mq
    assert 'string bg=NXS_UI_PREFIX+"status_bg"' in mq

def test_ea_delivery_uses_project_assets_path():
    text = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert 'Path(__file__).resolve().parents[1] / "assets" / "autotrade" / "NEXUS_AutoTrade.ex5"' in text
    assert "settings.autotrade_ex5_release_enabled" in text
