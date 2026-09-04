from __future__ import annotations

from pathlib import Path


ACCOUNT = Path("app/services/account_runtime.py").read_text(encoding="utf-8")
PRICING = Path("app/services/pricing_admin_runtime.py").read_text(encoding="utf-8")
RUN = Path("run.py").read_text(encoding="utf-8")


def test_account_screen_is_compact_and_keeps_detailed_validity_outside_account_hub():
    assert '"account"' in ACCOUNT

    # Product rule: AutoTrade management and Buy/Renew are Home actions, not
    # duplicate Account-menu buttons.
    assert "client_autotrade_access" not in ACCOUNT
    assert '("💎 خرید / تمدید اشتراک", "vip")' not in ACCOUNT
    assert '("💎 Buy / Renew Subscription", "vip")' not in ACCOUNT

    # Account may summarize entitlement state, but it must not expose detailed
    # license validity/key internals.
    assert "autotrade_expires_at" not in ACCOUNT
    assert "remaining_duration" not in ACCOUNT
    assert "license_key" not in ACCOUNT


def test_pricing_admin_supports_required_sources_and_refresh():
    for callback in (
        "pricing_provider:nobitex",
        "pricing_provider:wallex",
        "pricing_provider:international",
        "pricing_provider:custom",
        "pricing_refresh",
    ):
        assert callback in PRICING
    assert "rate_health()" in PRICING
    assert "last_rate_at" in PRICING
    assert "consecutive_failures" in PRICING


def test_pricing_callbacks_are_answered_once_before_screen_refresh():
    provider_start = PRICING.index("async def pricing_provider")
    refresh_start = PRICING.index("async def pricing_refresh", provider_start)
    provider_block = PRICING[provider_start:refresh_start]
    source_start = PRICING.index("async def pricing_source_save", refresh_start)
    refresh_block = PRICING[refresh_start:source_start]

    # Success paths explicitly answer once and call the screen helper directly,
    # instead of recursively invoking pricing_settings() which would answer again.
    assert "await _show(main, cb, bot)" in provider_block
    assert "await pricing_settings(cb, bot)" not in provider_block
    assert "await _show(main, cb, bot)" in refresh_block
    assert "await pricing_settings(cb, bot)" not in refresh_block


def test_specialized_runtimes_install_after_core_ux_patch():
    core = RUN.index("install_user_ux_hardening(main_module)")
    pricing = RUN.index("install_pricing_admin_runtime(main_module)")
    account = RUN.index("install_account_runtime(main_module)")
    poll = RUN.index("asyncio.run(main())")
    assert core < pricing < account < poll
