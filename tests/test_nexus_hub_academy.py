from __future__ import annotations

import pytest

from app.content.routing import (
    ACADEMY_CATEGORY_KEYS,
    PUBLIC_CATEGORY_KEYS,
    resolve_channel_destination,
    route_key_for_category,
)
from app.content.taxonomy import CATEGORIES
from app.ecosystem import (
    DEFAULT_ACADEMY_CHANNEL_ID,
    DEFAULT_ACADEMY_CHANNEL_URL,
    DEFAULT_NEXUS_FOLDER_URL,
    ecosystem_settings,
)
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


def test_official_academy_channel_is_embedded_as_default():
    assert DEFAULT_ACADEMY_CHANNEL_ID == "-1003994692349"
    assert DEFAULT_ACADEMY_CHANNEL_URL == "https://t.me/nexus_ict_learning"
    assert ecosystem_settings.academy_channel_id == DEFAULT_ACADEMY_CHANNEL_ID
    assert ecosystem_settings.academy_channel_url == DEFAULT_ACADEMY_CHANNEL_URL


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


def test_public_channel_has_exactly_five_allowed_categories():
    assert PUBLIC_CATEGORY_KEYS == frozenset({
        "daily_analysis",
        "quick_tip",
        "market_news",
        "important_news",
        "news_alert",
    })
    for key in PUBLIC_CATEGORY_KEYS:
        assert route_key_for_category(key) == "public"


def test_educational_categories_route_to_academy():
    assert ACADEMY_CATEGORY_KEYS == frozenset({
        "ict_education",
        "tools",
        "risk",
        "trade_review",
        "mindset",
    })
    for key in ACADEMY_CATEGORY_KEYS:
        assert route_key_for_category(key) == "academy"


def test_all_known_categories_are_explicitly_classified_once():
    assert PUBLIC_CATEGORY_KEYS.isdisjoint(ACADEMY_CATEGORY_KEYS)
    assert PUBLIC_CATEGORY_KEYS | ACADEMY_CATEGORY_KEYS == frozenset(CATEGORIES)


def test_unknown_category_fails_closed_instead_of_polluting_public():
    with pytest.raises(ValueError, match="unclassified content category"):
        route_key_for_category("future_unreviewed_category")


def test_academy_destination_uses_official_channel():
    class CoreSettings:
        public_channel_id = -1001111111111
        public_channel_url = "https://t.me/nexus_test_public"

    destination = resolve_channel_destination(CoreSettings(), "ict_education")
    assert destination.key == "academy"
    assert destination.chat_id == -1003994692349
    assert destination.channel_url == "https://t.me/nexus_ict_learning"


def test_quick_tip_destination_stays_public():
    class CoreSettings:
        public_channel_id = -1001111111111
        public_channel_url = "https://t.me/nexus_test_public"

    destination = resolve_channel_destination(CoreSettings(), "quick_tip")
    assert destination.key == "public"
    assert destination.chat_id == CoreSettings.public_channel_id
    assert destination.channel_url == CoreSettings.public_channel_url
