from __future__ import annotations

from app.content.routing import ACADEMY_CATEGORY_KEYS, route_key_for_category
from app.ecosystem import DEFAULT_NEXUS_FOLDER_URL, ecosystem_settings
from app.portal import build_nexus_folder_qr
from app.portal_runtime import build_nexus_main_menu


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return {
        button.callback_data
        for button in _buttons(markup)
        if button.callback_data
    }


def test_official_folder_url_is_embedded_as_safe_default():
    assert DEFAULT_NEXUS_FOLDER_URL == "https://t.me/addlist/ASXi4-91edg2YzA8"
    assert ecosystem_settings.folder_url.startswith("https://t.me/addlist/")


def test_main_menu_uses_folder_as_primary_gateway():
    markup = build_nexus_main_menu("fa")
    assert len(markup.inline_keyboard) == 5
    first = markup.inline_keyboard[0][0]
    assert first.text == "🚀 ورود به NEXUS"
    assert first.url == ecosystem_settings.folder_url


def test_regular_user_does_not_see_signal_or_autotrade_management():
    callbacks = _callbacks(build_nexus_main_menu("fa", has_autotrade=False))
    assert "client_signals" not in callbacks
    assert "client_autotrade_access" not in callbacks
    assert {
        "vip",
        "account",
        "guide_hub",
        "nexus_folder_qr",
        "support",
        "change_language",
    } <= callbacks


def test_autotrade_user_gets_direct_autotrade_control_only():
    markup = build_nexus_main_menu("fa", has_autotrade=True)
    callbacks = _callbacks(markup)
    assert "client_signals" not in callbacks
    assert "client_autotrade_access" in callbacks
    labels = {button.text for button in _buttons(markup)}
    assert "🤖 مدیریت AutoTrade" in labels
    assert not any("سیگنال عمومی" in text or "سیگنال VIP" in text for text in labels)


def test_legacy_signal_chooser_is_not_exposed_by_new_hub():
    for has_autotrade in (False, True):
        callbacks = _callbacks(build_nexus_main_menu("fa", has_autotrade=has_autotrade))
        assert "client_signals" not in callbacks


def test_qr_generator_returns_nontrivial_png():
    data = build_nexus_folder_qr(DEFAULT_NEXUS_FOLDER_URL)
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(data) > 10_000


def test_evergreen_education_routes_to_academy():
    expected = {"ict_education", "quick_tip", "tools", "risk", "trade_review", "mindset"}
    assert expected <= ACADEMY_CATEGORY_KEYS
    for key in expected:
        assert route_key_for_category(key) == "academy"


def test_analysis_and_news_stay_in_public_channel():
    for key in ("daily_analysis", "market_news", "important_news", "news_alert"):
        assert route_key_for_category(key) == "public"
