
import os
os.environ.setdefault("BOT_TOKEN","x")
os.environ.setdefault("ADMIN_IDS","1")
os.environ.setdefault("PUBLIC_CHANNEL_ID","1")
os.environ.setdefault("PUBLIC_CHANNEL_URL","https://t.me/x")
os.environ.setdefault("FREE_CHANNEL_URL","https://t.me/x")
os.environ.setdefault("VIP_CHANNEL_ID","2")
os.environ.setdefault("SUPPORT_USERNAME","x")
os.environ.setdefault("PAYMENT_CARD","123")
os.environ.setdefault("PAYMENT_OWNER","x")

try:
    from app import ui
except ModuleNotFoundError as exc:
    if exc.name == "aiogram":
        import pytest
        pytest.skip("aiogram is required for subscription UI tests", allow_module_level=True)
    raise

def buttons(markup):
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]

def test_subscription_page_has_exactly_three_products():
    fa = buttons(ui.subscription_service_menu("fa", False, False))
    products = [x for x in fa if x[1] in {"buyservice:VIP","buyservice:AUTO","buyservice:BUNDLE"}]
    assert [x[1] for x in products] == ["buyservice:VIP","buyservice:AUTO","buyservice:BUNDLE"]
    assert len(products) == 3

def test_subscription_page_state_labels():
    fa = buttons(ui.subscription_service_menu("fa", True, False))
    products = [(t, c) for t, c in fa if c.startswith("buyservice:")]
    assert [c for _, c in products] == ["buyservice:VIP", "buyservice:AUTO", "buyservice:BUNDLE"]
    assert len(products) == 3
    assert all(t in {"VIP", "AutoTrade", "VIP + AutoTrade"} for t, _ in products)
    assert "ارتقا" not in " ".join(t for t,c in fa)

def test_account_contains_payments_and_referral():
    fa = buttons(ui.account_menu("fa", True))
    codes = {c for _,c in fa}
    assert "my_payments" in codes
    assert "referral" in codes
    assert "vip" in codes
    assert "main" in codes

def test_referral_returns_to_account():
    fa = buttons(ui.referral_menu("fa", "https://t.me/x"))
    assert ("⬅️ حساب من", "account") in fa

def test_main_menu_has_single_subscription_entry():
    fa = buttons(ui.main_menu("fa"))
    assert ("💎 خرید اشتراک", "vip") in fa
    assert ("⭐ دعوت و امتیاز", "referral") not in fa
