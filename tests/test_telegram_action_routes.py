from app.ui import admin_menu, signal_center_menu


def _callbacks(markup):
    return {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }


def test_admin_menu_exposes_content_actions_in_both_languages():
    for lang in ("fa", "en"):
        callbacks = _callbacks(admin_menu(lang))
        assert "admin_group_content" in callbacks
        assert "admin_signals" in callbacks
        assert "admin_group_reports" in callbacks
        assert "admin_group_system" in callbacks


def test_signal_center_uses_same_analytics_route_in_both_languages():
    for lang in ("fa", "en"):
        callbacks = _callbacks(signal_center_menu(lang))
        assert "signal_analytics" in callbacks
        assert "admin_dashboard" not in callbacks
