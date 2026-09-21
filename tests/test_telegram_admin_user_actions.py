from __future__ import annotations

import asyncio
import importlib

from aiogram.types import CallbackQuery, User

import app.main as main
from app import customer_experience as customer_experience
from app.routers import analytics, subscriptions


def _callback_data(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def _walk_routers(router):
    yield router
    for child in getattr(router, "sub_routers", []):
        yield from _walk_routers(child)


def _runtime_routers():
    roots = [subscriptions.router, analytics.router, main.router]
    seen = set()
    for root in roots:
        for router in _walk_routers(root):
            marker = id(router)
            if marker in seen:
                continue
            seen.add(marker)
            yield router


async def _matching_handlers(callback_data: str):
    event = CallbackQuery(
        id="nexus-smoke",
        from_user=User(id=1, is_bot=False, first_name="Smoke"),
        chat_instance="nexus-smoke",
        data=callback_data,
    )
    matches = []
    for router in _runtime_routers():
        for handler in router.callback_query.handlers:
            # A no-filter callback handler would match everything and would hide
            # dead-button regressions, so only count explicit filtered handlers.
            if not handler.filters:
                continue
            try:
                passed, _ = await handler.check(event)
            except Exception:
                continue
            if passed:
                matches.append(getattr(handler.callback, "__name__", "<anonymous>"))
    return matches


def _assert_callbacks_routable(callbacks):
    failures = {}
    for callback_data in sorted(set(callbacks)):
        matches = asyncio.run(_matching_handlers(callback_data))
        if not matches:
            failures[callback_data] = matches
    assert not failures, f"Callbacks without any runtime handler: {failures}"


def test_runtime_bootstrap_imports_without_starting_polling():
    runtime = importlib.import_module("run")
    assert runtime.main_module is main
    assert callable(runtime.main)


def test_effective_user_menu_callbacks_are_routable():
    importlib.import_module("run")

    # run.py installs customer_experience + customer_menu_runtime + UX patches.
    # Use the effective builders after those patches, not the legacy app.ui
    # builders, so intentionally removed features (for example Exchange)
    # do not produce false failures.
    markups = [
        customer_experience.customer_main_menu(
            "en",
            is_admin=False,
            has_vip=False,
        ),
        main.client_signal_menu("en", False, False),
        main.autotrade_user_menu("en"),
        main.account_menu("en", False, False),
        main.guide_hub_menu("en"),
    ]

    callbacks = [
        callback_data
        for markup in markups
        for callback_data in _callback_data(markup)
    ]
    _assert_callbacks_routable(callbacks)


def test_effective_admin_menu_callbacks_are_routable():
    importlib.import_module("run")

    markups = [
        main.admin_menu("en"),
        main.admin_users_group("en"),
        main.admin_finance_group("en"),
        main.admin_rewards_group("en"),
        main.admin_marketing_group("en"),
        main.admin_reports_group("en"),
        main.admin_system_group("en"),
        main.signal_center_menu("en"),
    ]

    callbacks = [
        callback_data
        for markup in markups
        for callback_data in _callback_data(markup)
    ]
    _assert_callbacks_routable(callbacks)


def test_common_dynamic_user_callbacks_are_routable():
    importlib.import_module("run")

    callbacks = [
        "my_payments:all",
        "my_payments:approved",
        "buyservice:VIP",
        "plan:TEST",
        "discount:none:TEST",
        "discount:promo:TEST",
        "method:TEST:usdt",
        "receipt:TEST:usdt",
    ]
    _assert_callbacks_routable(callbacks)


def test_common_dynamic_admin_callbacks_are_routable():
    importlib.import_module("run")

    callbacks = [
        "admuser:123",
        "admextend:123",
        "admpoints:123",
        "admlink:123",
        "admcancel:123",
        "planadm:TEST",
        "planaccess:TEST",
        "planent:vip:TEST",
        "planrenew:TEST",
        "planrenewset:TEST:10",
        "plantoggle:TEST",
        "discount_toggle:1",
        "campaign_toggle:1",
        "broadcast_target:all",
    ]
    _assert_callbacks_routable(callbacks)


def test_signal_reporting_menu_callbacks_are_routable():
    importlib.import_module("run")

    callbacks = [
        "admin_signals",
        "signal_active",
        "signal_closed",
        "signal_refresh",
        "signal_stats",
        "signal_analytics",
        "analytics:overview:7",
        "analytics:symbols:7",
        "analytics:trailing:7",
        "analytics:channels:7",
    ]
    _assert_callbacks_routable(callbacks)
