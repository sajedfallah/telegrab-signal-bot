from aiogram.fsm.state import State, StatesGroup


class Flow(StatesGroup):
    # Payments / client flows
    waiting_receipt = State()
    waiting_usdt_txid = State()
    waiting_promo = State()

    # Auto Trade / MT5 account lifecycle
    autotrade_account_change = State()
    autotrade_initial_account = State()

    # Admin marketing / loyalty
    admin_discount_code = State()
    admin_discount_percent = State()
    admin_discount_days = State()
    admin_discount_max = State()
    admin_reward_value = State()
    admin_campaign_title = State()
    admin_campaign_percent = State()
    admin_campaign_days = State()
    admin_campaign_max = State()
    admin_broadcast_message = State()

    # Subscription-plan management
    admin_plan_code = State()
    admin_plan_days = State()
    admin_plan_title_fa = State()
    admin_plan_title_en = State()
    admin_plan_irr = State()
    admin_plan_usdt = State()
    admin_plan_setup = State()
    admin_usdt_rate = State()
    admin_invoice_ttl = State()
    admin_rate_source = State()

    # Signal creation / lifecycle
    signal_chart = State()
    signal_symbol = State()
    signal_timeframe = State()
    signal_entry = State()
    signal_stop_limit = State()
    signal_sl = State()
    signal_tp_count = State()
    signal_tp_value = State()
    signal_position = State()
    signal_risk = State()
    signal_partial = State()
    signal_trailing = State()
    signal_update_tp = State()
    signal_update_sl = State()
    signal_close_exit = State()
    signal_close_chart = State()
