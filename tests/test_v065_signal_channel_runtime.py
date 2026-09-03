from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.services.signal_channel_runtime import _client_signal_menu


RUN = Path("run.py").read_text(encoding="utf-8")
RUNTIME = Path("app/services/signal_channel_runtime.py").read_text(encoding="utf-8")


def _fake_main():
    return SimpleNamespace(
        settings=SimpleNamespace(
            free_channel_url="https://t.me/nexus_public_signals",
            public_channel_url="https://t.me/nexus_general_public",
        )
    )


def test_public_signal_button_links_directly_to_free_signal_channel():
    main = _fake_main()
    markup = _client_signal_menu(main, "fa", has_vip=False, has_autotrade=False)

    public_button = markup.inline_keyboard[0][0]
    assert public_button.text == "🎯 سیگنال عمومی"
    assert public_button.url == main.settings.free_channel_url
    assert public_button.callback_data is None


def test_signals_menu_never_links_to_general_public_channel():
    main = _fake_main()
    markup = _client_signal_menu(main, "fa", has_vip=True, has_autotrade=True)

    urls = [
        button.url
        for row in markup.inline_keyboard
        for button in row
        if button.url
    ]
    assert main.settings.free_channel_url in urls
    assert main.settings.public_channel_url not in urls


def test_vip_and_autotrade_actions_remain_internal_callbacks():
    markup = _client_signal_menu(_fake_main(), "fa", has_vip=True, has_autotrade=True)
    second_row = markup.inline_keyboard[1]
    assert [button.callback_data for button in second_row] == [
        "client_vip_access",
        "client_autotrade_access",
    ]


def test_runtime_is_installed_before_polling_and_legacy_public_handler_is_replaced():
    assert "install_signal_channel_runtime(main_module)" in RUN
    assert RUN.index("install_signal_channel_runtime(main_module)") < RUN.index("asyncio.run(main())")
    assert '!= "public_channel"' in RUNTIME
    assert 'F.data == "public"' in RUNTIME
    assert "FREE_CHANNEL_URL" in RUNTIME
    assert "general-public=join-gate-only" in RUNTIME
