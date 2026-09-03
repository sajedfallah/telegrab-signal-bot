from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.services.license_service import AccessSnapshot
from app.services.license_view import remaining_duration_text, render_autotrade_license


TZ = ZoneInfo("Asia/Tehran")
NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


def test_remaining_duration_is_precise_to_minutes():
    assert remaining_duration_text("2026-09-05T15:45:00+00:00", lang="en", now=NOW) == "2d 3h 45m"
    assert remaining_duration_text("2026-09-05T15:45:00+00:00", lang="fa", now=NOW) == "2 روز و 3 ساعت و 45 دقیقه"


def test_inactive_license_returns_purchase_guidance():
    snap = AccessSnapshot(False, False, False, None, None, None, None)
    text, cta = render_autotrade_license(
        snap,
        license_key=None,
        mt5_account=None,
        plan=None,
        timezone_obj=TZ,
        lang="fa",
        now=NOW,
    )
    assert cta is True
    assert "غیرفعال" in text
    assert "خریداری/تمدید" in text


def test_active_license_includes_plan_dates_remaining_account_and_key():
    snap = AccessSnapshot(
        True,
        True,
        True,
        "AUTO1M",
        "payment",
        "2026-10-03T12:00:00+00:00",
        7,
        starts_at="2026-09-03T12:00:00+00:00",
        vip_expires_at="2026-10-03T12:00:00+00:00",
        autotrade_expires_at="2026-10-03T12:00:00+00:00",
    )
    plan = {"title_fa": "VIP + AutoTrade یک‌ماهه", "title_en": "VIP + AutoTrade 1 Month", "code": "AUTO1M"}
    text, cta = render_autotrade_license(
        snap,
        license_key="NX-KEY-123",
        mt5_account="80150619",
        plan=plan,
        timezone_obj=TZ,
        lang="fa",
        now=NOW,
    )
    assert cta is False
    assert "فعال" in text
    assert "VIP + AutoTrade یک‌ماهه" in text
    assert "2026/09/03" in text
    assert "2026/10/03" in text
    assert "30 روز" in text
    assert "80150619" in text
    assert "NX-KEY-123" in text


def test_active_entitlement_without_bound_account_does_not_crash():
    snap = AccessSnapshot(
        True,
        False,
        True,
        "AEX1M",
        "payment",
        "2026-10-03T12:00:00+00:00",
        8,
        starts_at="2026-09-03T12:00:00+00:00",
        autotrade_expires_at="2026-10-03T12:00:00+00:00",
    )
    text, cta = render_autotrade_license(
        snap,
        license_key=None,
        mt5_account=None,
        plan={"title_en": "AutoTrade 1 Month", "code": "AEX1M"},
        timezone_obj=TZ,
        lang="en",
        now=NOW,
    )
    assert cta is False
    assert "Not registered" in text
    assert "Pending MT5 account registration" in text
