import os
os.environ.setdefault('BOT_TOKEN','x')
os.environ.setdefault('ADMIN_IDS','1')
os.environ.setdefault('PUBLIC_CHANNEL_ID','1')
os.environ.setdefault('PUBLIC_CHANNEL_URL','https://t.me/x')
os.environ.setdefault('FREE_CHANNEL_URL','https://t.me/x')
os.environ.setdefault('VIP_CHANNEL_ID','2')
os.environ.setdefault('SUPPORT_USERNAME','x')
os.environ.setdefault('PAYMENT_CARD','123')
os.environ.setdefault('PAYMENT_OWNER','x')

try:
    from app import ui
except ModuleNotFoundError as exc:
    if exc.name == "aiogram":
        import pytest
        pytest.skip("aiogram is required for UI localization tests", allow_module_level=True)
    raise

BANNED = (
    'Signal','Center','Audit','CRM','Setup','Fee','Limit','Market','BUY','SELL',
    'LONG','SHORT','Break','Even','Partial','Close','Trailing','Stop','Update','Manual','Symbol',
    'Points','Referral','Waiting','List','Trial','Forex','Crypto','Back','Main','Menu','All',
    'Users','Plans','Pricing','Discount','Campaign','Broadcast','Report','Status','Database','Backup',
    'Change','Language','English','Approve','Reject','Enable','Disable','Renewal','Expiry','Dashboard',
    'Analytics','Quick','Active','Closed','Create','New','Confirm','Cancel','Publish','Retry','Access',
    'Revenue','Source','Toggle','Clear','Invoice','TTL','Proration'
)


def texts(markup):
    return [b.text for row in markup.inline_keyboard for b in row]


def assert_no_english(label, markup):
    joined=' | '.join(texts(markup))
    for word in BANNED:
        assert word not in joined, f'{label}: English UI token leaked into Persian menu: {word!r} -> {joined}'


def test_admin_menus_are_persian():
    funcs = [
        ui.admin_menu, ui.admin_users_group, ui.admin_finance_group, ui.admin_rewards_group,
        ui.admin_content_group, ui.admin_marketing_group, ui.admin_reports_group,
        ui.admin_system_group, ui.signal_center_menu, ui.discounts_menu,
        ui.reward_settings_menu, ui.campaign_menu, ui.campaign_audience_menu,
        ui.broadcast_target_menu, ui.broadcast_confirm_menu, ui.admin_crm_menu,
    ]
    for fn in funcs:
        assert_no_english(fn.__name__, fn('fa'))


def test_payment_and_signal_menus_are_persian():
    assert_no_english('payment_method', ui.payment_method('fa', 'AUTO1M'))
    assert_no_english('payment_actions', ui.payment_actions('fa', 'AUTO1M', 'usdt'))
    assert_no_english('admin_payment', ui.admin_payment(1, 'fa'))
    assert_no_english('signal_market_menu', ui.signal_market_menu('fa'))
    assert_no_english('signal_direction_menu', ui.signal_direction_menu('fa', 'FOREX'))
    assert_no_english('signal_order_type_menu', ui.signal_order_type_menu('fa'))
    assert_no_english('signal_manage_menu', ui.signal_manage_menu(1, 'fa'))
    labels = [b.text for row in ui.subscription_service_menu('fa', False, False).inline_keyboard for b in row]
    assert labels[:3] == ["VIP", "AutoTrade", "VIP + AutoTrade"]
    assert_no_english('my_payments_menu', ui.my_payments_menu('fa'))
