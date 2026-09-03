from __future__ import annotations

from pathlib import Path


PATCH = Path("app/ux_runtime_patch.py").read_text(encoding="utf-8")
RUN = Path("run.py").read_text(encoding="utf-8")


def _block(start_marker: str, end_marker: str) -> str:
    start = PATCH.index(start_marker)
    end = PATCH.index(end_marker, start)
    return PATCH[start:end]


def test_runtime_hardening_installs_before_polling():
    assert "install_user_ux_hardening(main_module)" in RUN
    assert RUN.index("install_user_ux_hardening(main_module)") < RUN.index("asyncio.run(main())")


def test_customer_autotrade_menu_has_no_exchange_action():
    block = _block("def _autotrade_user_menu", "async def _screen")
    assert "autotrade_exchange" not in block
    assert "Connect Exchange" not in block
    assert "اتصال صرافی" not in block
    assert "autotrade_license" in block
    assert "autotrade_download_mt5" in block


def test_exchange_callback_and_credential_handlers_are_unregistered():
    for name in (
        "autotrade_exchange",
        "exchange_select",
        "exchange_disconnect",
        "exchange_retest",
        "exchange_api_key_input",
        "exchange_api_secret_input",
        "exchange_api_passphrase_input",
    ):
        assert f'"{name}"' in PATCH
    install_block = PATCH[PATCH.index("def install(main_module)"):]
    assert "EXCHANGE_CALLBACK_HANDLER_NAMES" in install_block
    assert "EXCHANGE_MESSAGE_HANDLER_NAMES" in install_block
    assert "_remove_handlers" in install_block


def test_license_details_are_centralized_in_replacement_handlers():
    block = _block("def _register_customer_handlers", "def _register_guide_handlers")
    assert "render_autotrade_license" in block
    assert "autotrade_expires_at" not in block  # renderer owns detailed date formatting
    assert "برای مشاهده License Key" in block
    assert "My License" in block


def test_installer_and_license_issuance_share_reliable_delivery_path():
    block = _block("def _install_delivery", "async def _send_mt5_video_guide")
    assert "deliver_mt5_package" in block
    assert "main._send_mt5_installer_and_help = send_mt5_package" in block
    assert "main.send_autotrade_license = send_autotrade_license" in block
    assert "await send_mt5_package" in block
    assert "AutoTradeDeliveryError" in block


def test_pricing_manager_has_presets_refresh_and_daily_monitor():
    pricing_block = _block("def _register_pricing_handlers", "def _install_rate_worker")
    assert "pricing_provider:nobitex" in pricing_block
    assert "pricing_provider:wallex" in pricing_block
    assert "pricing_provider:international" in pricing_block
    assert "pricing_provider:custom" in pricing_block
    assert "pricing_refresh" in pricing_block
    worker_block = _block("def _install_rate_worker", "def _install_message_lifecycle")
    assert "usdt_rate_worker" in worker_block


def test_transient_messages_are_forced_to_at_least_30_seconds():
    block = _block("def _install_message_lifecycle", "def install(main_module)")
    assert "DEFAULT_INFO_TTL_SECONDS" in block
    assert "max(DEFAULT_INFO_TTL_SECONDS, int(delay))" in block
