from __future__ import annotations

import inspect

from app.miniapp_trades import _live_item, trade_detail, trades


def test_trades_api_never_accepts_frontend_account_number_for_authorization():
    params = inspect.signature(trades).parameters
    assert "account_number" not in params
    assert "mt5_account" not in params


def test_trade_detail_query_is_scoped_to_authenticated_telegram_owner():
    source = inspect.getsource(trade_detail)
    assert "WHERE id=? AND telegram_id=?" in source


def test_live_trade_projection_does_not_expose_internal_control_fields():
    item = _live_item({
        "account_number": "12345678",
        "identifier": "p1",
        "ticket": "987",
        "signal_code": "42",
        "symbol": "XAUUSD",
        "direction": "BUY",
        "volume": 0.01,
        "entry_price": 3500,
        "current_price": 3505,
        "stop_loss": 3490,
        "take_profit": 3520,
        "profit": 5.2,
        "magic": 991122,
        "nexus_managed": 1,
        "order_type": "MARKET",
        "status": "OPEN",
        "broker": "Broker",
        "server": "Server",
        "last_seen_at": "2026-09-10T00:00:00+00:00",
    })
    assert item["ticket"] == "987"
    assert item["profit"] == 5.2
    assert "account_number" not in item
    assert "magic" not in item
    assert "nexus_managed" not in item


def test_combined_api_exposes_customer_trades_and_health_resources():
    from app.combined_api import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/miniapp/api/autotrade/status" in paths
    assert "/miniapp/api/trades" in paths
    assert "/miniapp/api/trades/{execution_id}" in paths
