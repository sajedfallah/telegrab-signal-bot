from __future__ import annotations

from pathlib import Path

from app import miniapp_home, miniapp_product_intelligence, miniapp_signals


def _text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_home_hierarchy_is_daily_utility_first_and_entry_is_global():
    experience = {"segment": "VIP", "lifecycle": "ACTIVE", "entitlements": {"vip": True, "autotrade": False}}
    order = miniapp_home._section_order(experience, [], {"kind": "UPGRADE"}, {"market_insight": None, "academy": None})
    assert order[0] == "spotlight"
    assert order.index("today") < order.index("recent_signals") < order.index("performance") < order.index("offer")
    assert miniapp_home.NEXUS_ENTRY_URL == "https://t.me/nexus_publicc"


def test_home_admin_content_is_optional_and_never_fabricated_by_section_order():
    experience = {"segment": "GUEST", "lifecycle": "GUEST", "entitlements": {"vip": False, "autotrade": False}}
    order = miniapp_home._section_order(experience, [], None, {"market_insight": None, "academy": None})
    assert "market_insight" not in order
    assert "academy" not in order
    src = _text("app/miniapp_product_intelligence.py")
    assert "There is intentionally no synthetic market insight fallback" in src


def test_analytics_metadata_is_capped_and_event_names_are_whitelisted():
    meta = miniapp_product_intelligence._safe_metadata({f"k{i}": "x" * 500 for i in range(20)})
    assert len(meta) == 12
    assert all(len(value) <= 256 for value in meta.values())
    assert "product_swipe" in miniapp_product_intelligence.ALLOWED_EVENTS
    assert "trade_detail_view" in miniapp_product_intelligence.ALLOWED_EVENTS


def test_content_audience_matches_segment_or_lifecycle():
    experience = {"segment": "VIP", "lifecycle": "EXPIRING"}
    assert miniapp_product_intelligence._audience_matches("ALL", experience)
    assert miniapp_product_intelligence._audience_matches("VIP", experience)
    assert miniapp_product_intelligence._audience_matches("EXPIRING", experience)
    assert not miniapp_product_intelligence._audience_matches("BUNDLE", experience)


def test_signal_result_taxonomy_supports_terminal_non_pnl_states():
    base = {"status": "CLOSED", "result_value": None, "result_unit": None}
    assert miniapp_signals._result_meta(base | {"close_reason": "CANCELLED"})["result"] == "CANCELLED"
    assert miniapp_signals._result_meta(base | {"close_reason": "EXPIRED"})["result"] == "EXPIRED"
    assert miniapp_signals._result_meta(base | {"close_reason": "PARTIAL_CLOSE"})["result"] == "PARTIAL"


def test_signal_detail_exposes_execution_truth_without_guessing_disconnect_reason():
    src = _text("app/miniapp_signals.py")
    assert "autotrade_signal_receipts" in src
    assert "autotrade_trade_executions" in src
    assert '"execution_state": "NOT_RECEIVED"' in src
    assert "رسید دریافت سیگنال از EA ثبت نشده است" in src
    assert "Expert هنگام انتشار Signal متصل نبود" not in src


def test_trade_detail_has_live_route_source_signal_and_execution_timeline():
    src = _text("app/miniapp_trades.py")
    assert '@router.get("/trades/live/{ticket}")' in src
    assert '"source_signal"' in src
    assert '"timeline"' in src
    assert "realized_r" in src


def test_account_autotrade_is_state_aware():
    src = _text("app/miniapp_account.py")
    for state in ("NO_SUBSCRIPTION", "LICENSE_REQUIRED", "MT5_REQUIRED", "CONNECTION_ISSUE", "CONNECTED"):
        assert state in src
    for cta in ("خرید AutoTrade", "راه‌اندازی AutoTrade", "معاملات من", "رفع مشکل اتصال"):
        assert cta in src


def test_frontend_has_polish_intelligence_features_and_no_css_only_access_gate():
    home = _text("miniapp/home-v2.js")
    signals = _text("miniapp/signals-v2.js")
    pricing = _text("miniapp/pricing-v2.js")
    account = _text("miniapp/account-v2.js")
    trades = _text("miniapp/trades-v2.js")
    product = _text("miniapp/product-intelligence.js")
    css = _text("miniapp/polish-v3.css")

    assert "ورود به نکسوس" in home and "normalizedOrder" in home
    assert "Win Rate" in home and ".slice(0, 3)" in home
    assert "وضعیت" in signals and "نوع دسترسی" in signals and "عملکرد NEXUS" in signals
    assert "CANCELLED" in signals and "EXPIRED" in signals and "PARTIAL" in signals
    assert "const categories = ['bundle', 'vip', 'autotrade'];" in pricing
    assert "product_swipe" in pricing and "مشاهده همه امکانات" in pricing
    assert "normalizeBidi" in account and "account-owner-name" in account
    assert "data-live-ticket" in trades and "Execution Timeline" in trades
    assert "miniapp_open" in product and "openNotifications" in product
    assert "--nexus-border-outer" in css and "2px solid var(--nexus-border-outer)" in css
    assert ".direction-chip.sell" in css and ".direction-chip.buy" in css


def test_shell_loads_notification_center_polish_layer_and_new_cache_key():
    html = _text("miniapp/index.html")
    assert 'id="notificationsBtn"' in html
    assert './product-intelligence.js?v=20260910-1033' in html
    assert './polish-v3.css?v=20260910-1033' in html
    assert './assets/brand/nexus-logo.svg?v=20260910-1033' in html


def test_bottom_nav_remains_server_lifecycle_authoritative():
    src = _text("app/miniapp_experience.py")
    assert 'label_fa="معاملات"' in src
    assert 'label_fa="ارتقا"' in src
    assert 'label_fa="پلن‌ها"' in src
