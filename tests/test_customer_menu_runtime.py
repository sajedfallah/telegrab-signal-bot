from app import customer_menu_runtime as menu


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def test_customer_home_order_without_top_level_autotrade_status():
    markup = menu.customer_main_menu("fa", is_admin=False, has_vip=False)
    rows = markup.inline_keyboard

    assert rows[0][0].text == "🚪 ورود به نکسوس"
    assert rows[1][0].text == "🔒 کانال سیگنال VIP"
    assert rows[1][0].callback_data == "customer_vip_hub"

    labels = {button.text for button in _buttons(markup)}
    assert "📊 سیگنال" not in labels
    assert "⚙️ وضعیت AutoTrade" not in labels
    assert "❓ سوالات متداول" not in labels
    assert "🛟 پشتیبانی" in labels


def test_autotrade_status_is_nested_under_vip_hub():
    submenu = menu.vip_hub_menu("fa", has_vip=False, has_autotrade=False)
    buttons = _buttons(submenu)
    labels = {button.text for button in buttons}
    callbacks = {button.callback_data for button in buttons if button.callback_data}

    assert "🔒 ورود به کانال سیگنال VIP" in labels
    assert "🔴 وضعیت AutoTrade" in labels
    assert "vip_channel_access" in callbacks
    assert "customer_autotrade_status" in callbacks


def test_faq_is_nested_under_support():
    support = menu.support_menu("fa")
    labels = {button.text for button in _buttons(support)}
    assert "🛟 ارتباط با پشتیبانی" in labels
    assert "❓ سوالات متداول" in labels

    faq = menu.faq_menu("fa")
    callbacks = {button.callback_data for button in _buttons(faq) if button.callback_data}
    assert "customer_support" in callbacks
