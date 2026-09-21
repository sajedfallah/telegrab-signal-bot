from __future__ import annotations

import importlib

import app.main as main
from app import ui
from app.routers import analytics, subscriptions


def _callback_names(router):
    return [
        getattr(handler.callback, "__name__", "")
        for handler in router.callback_query.handlers
    ]


def _callback_data(markup):
    values = []
    for row in markup.inline_keyboard:
        for button in row:
            if button.callback_data:
                values.append(button.callback_data)
    return values


def test_runtime_bootstrap_imports_without_starting_polling():
    runtime = importlib.import_module("run")
    assert runtime.main_module is main
    assert callable(runtime.main)


def test_core_user_actions_are_registered_after_runtime_patches():
    importlib.import_module("run")
    names = set(_callback_names(main.router))

    required = {
        "menu",
        "change_language",
        "client_signals",
        "client_vip_access",
        "client_autotrade_access",
        "autotrade_status",
        "autotrade_open",
        "autotrade_history",
        "autotrade_today",
        "autotrade_license",
        "autotrade_download_mt5",
        "autotrade_account_change",
        "autotrade_exchange",
        "autotrade_help",
        "public",
        "vip",
        "account",
        "my_payments",
        "referral",
        "support",
    }

    missing = sorted(required - names)
    assert not missing, f"Missing user callback handlers: {missing}"


def test_core_admin_actions_are_registered_after_runtime_patches():
    importlib.import_module("run")
    names = set(_callback_names(main.router))

    required = {
        "admin",
        "admin_group_users",
        "admin_group_finance",
        "admin_group_rewards",
        "admin_group_marketing",
        "admin_group_reports",
        "admin_group_system",
        "admin_users",
        "admin_subs",
        "admin_plans",
        "admin_pending",
        "admin_discounts",
        "admin_rewards",
        "admin_campaigns",
        "admin_broadcast",
        "admin_stats",
        "admin_dashboard",
        "admin_audit",
        "admin_backup",
        "admin_crm",
        "admin_retention",
        "admin_levels",
        "admin_signals",
        "signal_active",
        "signal_closed",
        "signal_refresh",
        "signal_stats",
        "report_daily_now",
        "report_weekly_now",
        "pricing_settings",
    }

    missing = sorted(required - names)
    assert not missing, f"Missing admin callback handlers: {missing}"


def test_user_menus_expose_only_callbacks_backed_by_core_handlers():
    importlib.import_module("run")
    names = set(_callback_names(main.router))

    markups = [
        ui.main_menu("en", False),
        ui.client_signal_menu("en", False, False),
        ui.autotrade_user_menu("en"),
        ui.account_menu("en", False, False),
        ui.guide_hub_menu("en"),
    ]

    callbacks = {
        value
        for markup in markups
        for value in _callback_data(markup)
    }

    # Dynamic/prefix callbacks are tested by their dedicated handler families.
    exact_callbacks = {
        value for value in callbacks
        if ":" not in value
    }

    callback_to_handler = {
        "main": "menu",
        "change_language": "change_language",
        "client_signals": "client_signals",
        "client_vip_access": "client_vip_access",
        "client_autotrade_access": "client_autotrade_access",
        "autotrade_status": "autotrade_status",
        "autotrade_open": "autotrade_open",
        "autotrade_history": "autotrade_history",
        "autotrade_today": "autotrade_today",
        "autotrade_license": "autotrade_license",
        "autotrade_download_mt5": "autotrade_download_mt5",
        "autotrade_account_change": "autotrade_account_change",
        "autotrade_exchange": "autotrade_exchange",
        "autotrade_help": "autotrade_help",
        "public": "public",
        "vip": "vip",
        "account": "account",
        "my_payments": "my_payments",
        "referral": "referral",
        "support": "support",
        "guide_hub": "guide_hub",
        "guide_intro": "guide_page",
        "guide_mt5": "guide_page",
    }

    missing_mapping = sorted(exact_callbacks - callback_to_handler.keys())
    assert not missing_mapping, f"Unmapped user callbacks: {missing_mapping}"

    missing_handlers = sorted(
        callback
        for callback, handler in callback_to_handler.items()
        if callback in exact_callbacks and handler not in names
    )
    assert not missing_handlers, f"User callbacks without registered handlers: {missing_handlers}"


def test_admin_menu_callbacks_have_registered_handlers():
    importlib.import_module("run")
    names = set(_callback_names(main.router))

    markups = [
        ui.admin_menu("en"),
        ui.admin_users_group("en"),
        ui.admin_finance_group("en"),
        ui.admin_rewards_group("en"),
        ui.admin_marketing_group("en"),
        ui.admin_reports_group("en"),
        ui.admin_system_group("en"),
        ui.signal_center_menu("en"),
    ]

    callbacks = {
        value
        for markup in markups
        for value in _callback_data(markup)
        if ":" not in value
    }

    callback_to_handler = {
        "admin": "admin",
        "main": "menu",
        "change_language": "change_language",
        "admin_group_users": "admin_group_users",
        "admin_group_finance": "admin_group_finance",
        "admin_group_rewards": "admin_group_rewards",
        "admin_group_marketing": "admin_group_marketing",
        "admin_group_reports": "admin_group_reports",
        "admin_group_system": "admin_group_system",
        "admin_users": "admin_users",
        "admin_subs": "admin_subs",
        "admin_levels": "admin_levels",
        "admin_retention": "admin_retention",
        "admin_pending": "admin_pending",
        "admin_plans": "admin_plans",
        "admin_discounts": "admin_discounts",
        "pricing_settings": "pricing_settings",
        "admin_rewards": "admin_rewards",
        "ref_leaderboard": "ref_leaderboard",
        "admin_campaigns": "admin_campaigns",
        "admin_broadcast": "admin_broadcast",
        "report_daily_now": "report_daily_now",
        "report_weekly_now": "report_weekly_now",
        "admin_stats": "admin_stats",
        "admin_dashboard": "admin_dashboard",
        "admin_audit": "admin_audit",
        "signal_stats": "signal_stats",
        "admin_backup": "admin_backup",
        "admin_crm": "admin_crm",
        "admin_signals": "admin_signals",
        "signal_active": "signal_active",
        "signal_closed": "signal_closed",
        "signal_refresh": "signal_refresh",
        "signal_analytics": None,
    }

    missing_mapping = sorted(callbacks - callback_to_handler.keys())
    assert not missing_mapping, f"Unmapped admin callbacks: {missing_mapping}"

    missing_handlers = sorted(
        callback
        for callback, handler in callback_to_handler.items()
        if callback in callbacks and handler is not None and handler not in names
    )
    assert not missing_handlers, f"Admin callbacks without registered handlers: {missing_handlers}"

    if "signal_analytics" in callbacks:
        assert analytics.router.callback_query.handlers, "Analytics router has no callback handlers"


def test_subscription_admin_router_is_registered_and_nonempty():
    assert subscriptions.router.callback_query.handlers
    callback_names = set(_callback_names(subscriptions.router))
    assert {
        "plan_access",
        "plan_entitlement_toggle",
        "plan_renewal_menu",
        "plan_renewal_set",
    } <= callback_names
