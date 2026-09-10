from __future__ import annotations

from pathlib import Path

from app import miniapp_purchase_flow


def _text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_combined_api_exposes_purchase_admin_and_meta_routes():
    from app.combined_api import app

    paths = {getattr(route, "path", "") for route in app.routes}
    required = {
        "/miniapp/api/purchase/receipts",
        "/miniapp/api/purchase/status",
        "/miniapp/api/purchase/payments/{payment_id}/retry",
        "/miniapp/api/purchase/meta-account",
        "/miniapp/api/admin/purchase/payments",
        "/miniapp/api/admin/purchase/payments/{payment_id}/receipt",
        "/miniapp/api/admin/purchase/payments/{payment_id}/approve",
        "/miniapp/api/admin/purchase/payments/{payment_id}/reject",
    }
    assert required <= paths


def test_vip_only_does_not_collect_unnecessary_metatrader_secret():
    vip, auto = miniapp_purchase_flow._plan_flags("VIP1M")
    assert vip is True
    assert auto is False


def test_bundle_requires_metatrader_onboarding():
    vip, auto = miniapp_purchase_flow._plan_flags("AUTO1M")
    assert vip is True
    assert auto is True


def test_investor_password_is_not_persisted_in_onboarding_schema():
    src = _text("app/miniapp_purchase_flow.py")
    schema = src.split("CREATE TABLE IF NOT EXISTS miniapp_meta_onboarding", 1)[1].split('"""', 1)[0]
    assert "investor_password" not in schema
    assert "investor_password" in src
    assert "Master Password" not in src


def test_payment_approval_activates_license_and_rejection_requires_reason():
    src = _text("app/miniapp_purchase_flow.py")
    assert "license_service.activate_payment(pay)" in src
    assert 'db.review_payment(payment_id, "approved"' in src
    assert 'db.review_payment(payment_id, "rejected"' in src
    assert "reason: str = Field(min_length=3" in src
    assert "RESUBMIT_RECEIPT" in src


def test_meta_validation_never_fabricates_mt4_execution_license():
    src = _text("app/miniapp_purchase_flow.py")
    assert "MT4_EXECUTION_BRIDGE_REQUIRED" in src
    assert "never fabricate a usable MT4 key" in src
    assert "db.issue_autotrade_license_for_account" in src


def test_safari_safe_logo_contains_no_embedded_bitmap_data_uri():
    logo = _text("miniapp/assets/brand/nexus-mark.svg")
    assert "data:image" not in logo
    assert "<image" not in logo
    assert "linearGradient" in logo


def test_shell_loads_locale_purchase_ui_and_new_logo_with_fresh_cache_key():
    html = _text("miniapp/index.html")
    assert "./assets/brand/nexus-mark.svg?v=20260910-1215" in html
    assert "./locale-v4.js?v=20260910-1215" in html
    assert "./ui-v4.css?v=20260910-1215" in html
    assert "./purchase-flow-v4.js?v=20260910-1215" in html
    assert "./compat-v4.js?v=20260910-1215" in html


def test_locale_layer_forces_tehran_persian_calendar_and_repairs_mojibake():
    src = _text("miniapp/locale-v4.js")
    assert "Asia/Tehran" in src
    assert "fa-IR-u-ca-persian" in src
    assert "repairMojibake" in src
    assert "TextDecoder('utf-8'" in src


def test_purchase_ui_uses_persian_errors_admin_review_and_secure_password_field():
    src = _text("miniapp/purchase-flow-v4.js")
    assert "بررسی رسیدهای پرداخت" in src
    assert "تأیید پرداخت" in src
    assert "دلیل رد رسید" in src
    assert "ارسال مجدد رسید" in src
    assert 'type="password"' in src
    assert "Investor / Read-only" in src
    assert "رمز اصلی معامله" in src
    assert "/purchase/meta-account" in src
