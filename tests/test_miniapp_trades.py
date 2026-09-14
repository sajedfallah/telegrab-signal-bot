from __future__ import annotations

import inspect

from app.miniapp_trades import _history, _history_item, _live_item, trade_detail, trades


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


def test_closed_history_projects_only_latest_close_per_ticket():
    source = inspect.getsource(_history)
    assert "UPPER(COALESCE(e.event_type,''))='CLOSE'" in source
    assert "ROW_NUMBER() OVER" in source
    assert "PARTITION BY e.ticket" in source
    assert "WHERE rn=1" in source
    # Lifecycle rows stay in the durable ledger; only the Closed-tab projection is collapsed.
    assert "DELETE" not in source.upper()


def test_close_history_card_uses_closed_status_not_processing_state():
    item = _history_item({
        "id": 123,
        "signal_id": 43,
        "ticket": "95697734",
        "event_type": "close",
        "symbol": "XAUUSD.EC",
        "direction": "LONG",
        "volume": 0.02,
        "entry_price": 4278.85,
        "stop_loss": 4303.19,
        "take_profit": 0.0,
        "exit_price": 4310.0,
        "profit": 62.3,
        "gross_profit": 62.3,
        "commission": 0.0,
        "swap": 0.0,
        "slippage": 0.0,
        "risk_cash": 0.0,
        "realized_r": None,
        "position_id": "p1",
        "deal_id": "d1",
        "status": "UPDATED",
        "error_text": None,
        "created_at": "2026-09-14T16:00:00+00:00",
        "updated_at": "2026-09-14T16:00:01+00:00",
    })
    assert item["event_type"] == "CLOSE"
    assert item["status"] == "CLOSED"
    assert item["ticket"] == "95697734"


def test_combined_api_exposes_customer_trades_and_health_resources():
    from app.combined_api import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/miniapp/api/autotrade/status" in paths
    assert "/miniapp/api/trades" in paths
    assert "/miniapp/api/trades/{execution_id}" in paths
