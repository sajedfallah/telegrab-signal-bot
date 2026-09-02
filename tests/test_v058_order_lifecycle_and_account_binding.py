
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def read(rel): return (ROOT/rel).read_text(encoding="utf-8")

def test_all_five_order_types_are_supported_end_to_end():
    ui=read("app/ui.py")
    main=read("app/main.py")
    tm=read("mt5/NEXUS_AutoTrade/Include/TradeManager.mqh")
    ea=read("mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5")
    for t in ["MARKET","BUY_LIMIT","SELL_LIMIT","BUY_STOP","SELL_STOP"]:
        assert f"sigorder:{t}" in ui or t=="MARKET"
        assert t in tm or t=="MARKET"
    for t in ["ORDER_TYPE_BUY_LIMIT","ORDER_TYPE_SELL_LIMIT","ORDER_TYPE_BUY_STOP","ORDER_TYPE_SELL_STOP"]:
        assert t in ea

def test_pending_lifecycle_has_cancel_and_expire_events():
    api=read("app/autotrade/api.py")
    db=read("app/db.py")
    main=read("app/main.py")
    ea=read("mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5")
    for token in ['"CANCEL"', '"EXPIRE"']:
        assert token in api
        assert token in db
        assert token in main
    assert "TRADE_TRANSACTION_ORDER_DELETE" in ea
    assert "ORDER_REASON_EXPIRATION" in ea

def test_account_change_request_and_admin_review_exist():
    db=read("app/db.py")
    api=read("app/autotrade/api.py")
    main=read("app/main.py")
    for token in ["autotrade_account_change_requests","request_mt5_account_change","review_mt5_account_change"]:
        assert token in db
    assert "/api/v1/autotrade/account-change" in api
    assert "/api/v1/admin/autotrade/account-change-requests" in api
    assert "admin_mt5_change_review:" in main

def test_payment_approval_requests_account_before_autotrade_license_delivery():
    main=read("app/main.py")
    pos=main.index('if access.autotrade:')
    block=main[pos:main.index('@router.callback_query(F.data.startswith("payno:"))',pos)]
    assert "prepare_autotrade_license_pending" in block
    assert "autotrade_submit_account" in block
    assert "send_autotrade_license(bot, user_id, lic)" not in block

def test_mt5_pending_payload_preserves_selected_order_type():
    api=read("app/autotrade/api.py")
    main=read("app/main.py")
    ea=read("mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5")
    assert "BUY_STOP_LIMIT|SELL_STOP_LIMIT" in api
    assert 'order_type=PendingOrderTypeName(ot)' in ea
    assert '"order_type"' in main

def test_signal_card_contains_core_fields_for_pending_orders():
    main=read("app/main.py")
    assert "SIGNAL" in main
    for field in ["Entry","Stop Loss","TP","R:R","Status"]:
        assert field in main
