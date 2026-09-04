from __future__ import annotations

import inspect

from app import customer_experience as cx
from app import customer_menu_runtime as menu_runtime


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def test_customer_home_starts_with_nexus_entry_and_has_no_generic_signals(monkeypatch):
    monkeypatch.setattr(cx, "NEXUS_FOLDER_URL", "https://t.me/nexus_publik")
    markup = menu_runtime.customer_main_menu("fa", is_admin=False, has_vip=False)
    buttons = _buttons(markup)
    labels = [b.text for b in buttons]

    first = markup.inline_keyboard[0][0]
    assert first.text == "🚪 ورود به نکسوس"
    assert first.url == "https://t.me/nexus_publik"

    assert "📊 سیگنال" not in labels
    assert "🔒 کانال سیگنال VIP" in labels
    assert "💎 خرید اشتراک" in labels
    assert "👤 حساب من" in labels
    assert "🎓 راهنما" in labels
    assert "🛟 پشتیبانی" in labels
    assert "❓ سوالات متداول" not in labels


def test_vip_button_unlocks_when_subscription_is_active():
    locked = _buttons(menu_runtime.customer_main_menu("fa", is_admin=False, has_vip=False))
    unlocked = _buttons(menu_runtime.customer_main_menu("fa", is_admin=False, has_vip=True))
    assert any(b.text == "🔒 کانال سیگنال VIP" for b in locked)
    assert any(b.text == "🔓 کانال سیگنال VIP" for b in unlocked)
    assert any(b.callback_data == "vip_channel_access" for b in unlocked)


def test_faq_lives_inside_support_submenu():
    home = _buttons(menu_runtime.customer_main_menu("fa", is_admin=False, has_vip=False))
    assert not any(b.callback_data == "faq" for b in home)
    assert any(b.callback_data == "customer_support" for b in home)

    support = _buttons(menu_runtime.support_menu("fa"))
    assert any(b.text == "❓ سوالات متداول" and b.callback_data == "faq" for b in support)
    assert any(b.text == "🛟 ارتباط با پشتیبانی" and b.url for b in support)

    faq = _buttons(menu_runtime.faq_menu("fa"))
    faq_callbacks = [
        b.callback_data
        for b in faq
        if b.callback_data and b.callback_data.startswith("faq:")
    ]
    assert len(faq_callbacks) >= 5
    assert "faq:subscription" in faq_callbacks
    assert "faq:vip" in faq_callbacks
    assert "faq:autotrade" in faq_callbacks
    assert any(b.callback_data == "customer_support" for b in faq)


def test_account_and_signal_menus_do_not_offer_alternate_purchase_entry_when_locked():
    account = _buttons(cx.customer_account_menu("fa", has_vip=False, has_autotrade=False))
    signals = _buttons(cx.customer_signal_menu("fa", has_vip=False, has_autotrade=False))
    assert not any(b.callback_data == "vip" for b in account)
    assert any(b.callback_data == "vip_locked_info" for b in account)
    assert any(b.callback_data == "autotrade_locked_info" for b in account)
    assert any(b.callback_data == "vip_locked_info" for b in signals)
    assert any(b.callback_data == "autotrade_locked_info" for b in signals)


def test_production_vip_channel_and_autotrade_server_contracts_are_explicit():
    assert cx.EXPECTED_VIP_CHANNEL_ID == -1003900670697
    assert cx.AUTOTRADE_PUBLIC_API_URL == "https://api.nexustrade.ir"


def test_post_purchase_bundle_contains_license_server_and_ex5_delivery():
    source = inspect.getsource(cx.send_autotrade_purchase_bundle)
    assert "مجوز من" in source
    assert "AUTOTRADE_PUBLIC_API_URL" in source
    assert "NEXUS_AutoTrade.ex5" in source
    assert "send_document" in source


def test_initial_mt5_binding_middleware_watches_canonical_fsm_state():
    source = inspect.getsource(cx.AutoTradePostLicenseDeliveryMiddleware)
    assert "Flow.autotrade_initial_account.state" in source
    assert "send_autotrade_purchase_bundle" in source
