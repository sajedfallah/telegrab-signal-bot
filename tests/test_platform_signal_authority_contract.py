from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    file = ROOT / path
    return file.read_text(encoding="utf-8") if file.exists() else ""


def test_telegram_miniapp_has_no_signal_issuance_authority() -> None:
    """Mini App is a consumer/management surface, never a signal issuer.

    Approved signal issuers are limited to MT5 Admin and Web Admin.  Keep this
    guard intentionally source-level so a future Mini App port cannot silently
    reintroduce a create/publish signal endpoint or UI action.
    """
    api = _text("app/miniapp_api.py")
    ui = _text("telegram-miniapp/src/App.tsx")

    forbidden_api_markers = (
        '@router.post("/admin/signals"',
        "def create_admin_signal(",
        "async def create_admin_signal(",
        "issue_mt5_admin_signal(",
        "miniapp_signal_published",
    )
    forbidden_ui_markers = (
        'act("/admin/signals"',
        "صدور سیگنال",
        "انتشار سیگنال",
    )

    for marker in forbidden_api_markers:
        assert marker not in api, f"Mini App must not expose signal issuance: {marker}"
    for marker in forbidden_ui_markers:
        assert marker not in ui, f"Mini App must not expose signal issuance UI: {marker}"


def test_integration_contract_declares_only_web_and_mt5_signal_issuers() -> None:
    contract = _text("INTEGRATION_EXECUTION_PLAN_FA.md")
    assert "MT5 Admin Expert" in contract
    assert "Web Admin Panel" in contract
    assert "Telegram Mini App **هیچ endpoint یا UI برای ایجاد/صدور/انتشار سیگنال ندارد**" in contract
