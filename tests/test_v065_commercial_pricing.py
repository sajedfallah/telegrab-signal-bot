from app.config import settings


def test_vip_pricing_rebased_to_19_usdt_monthly_base():
    plans = settings.plans
    assert plans["VIP1M"]["price_usdt"] == "19"
    assert plans["VIP3M"]["price_usdt"] == "52"
    assert plans["VIP6M"]["price_usdt"] == "98"
    assert plans["VIP12M"]["price_usdt"] == "182"


def test_autotrade_pricing_unchanged():
    plans = settings.plans
    assert plans["AEX1M"]["price_usdt"] == "5"
    assert plans["AEX3M"]["price_usdt"] == "14"
    assert plans["AEX6M"]["price_usdt"] == "27"
    assert plans["AEX12M"]["price_usdt"] == "49"


def test_bundle_pricing_is_vip_plus_autotrade():
    plans = settings.plans
    pairs = (
        ("VIP1M", "AEX1M", "AUTO1M"),
        ("VIP3M", "AEX3M", "AUTO3M"),
        ("VIP6M", "AEX6M", "AUTO6M"),
        ("VIP12M", "AEX12M", "AUTO12M"),
    )
    for vip_code, auto_code, bundle_code in pairs:
        expected = int(plans[vip_code]["price_usdt"]) + int(plans[auto_code]["price_usdt"])
        assert int(plans[bundle_code]["price_usdt"]) == expected
        assert plans[bundle_code]["vip_access"] is True
        assert plans[bundle_code]["autotrade_access"] is True
