from __future__ import annotations

from decimal import Decimal
import inspect

from app.miniapp_checkout import quote, serialize_quote


def test_order_summary_serializes_backend_quote_without_recalculating_total():
    result = serialize_quote({
        "plan": {"code": "AUTO3M", "fa": "VIP + AutoTrade", "en": "VIP + AutoTrade", "days": 90, "vip_access": True, "autotrade_access": True},
        "mode": "upgrade",
        "base_usdt": Decimal("83.00"),
        "setup_fee_usdt": Decimal("0.00"),
        "upgrade_credit_usdt": Decimal("12.50"),
        "discount_percent": Decimal("0.00"),
        "total_usdt": Decimal("70.50"),
        "duration_days": 90,
    })
    assert result["mode"] == "upgrade"
    assert result["base_usdt"] == "83.00"
    assert result["upgrade_credit_usdt"] == "12.50"
    assert result["total_usdt"] == "70.50"


def test_quote_endpoint_delegates_to_existing_pricing_engine():
    source = inspect.getsource(quote)
    assert "quote_purchase(uid, payload.plan_code.upper())" in source


def test_combined_api_exposes_order_summary_quote_resource():
    from app.combined_api import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/miniapp/api/quote" in paths
