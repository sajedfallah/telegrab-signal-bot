from __future__ import annotations

from pathlib import Path

from app.autotrade.telegram_anchor_guard import (
    _missing_anchor_channels,
    _required_channels,
)


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def test_v27_missing_anchor_detector_is_narrow_and_channel_scoped():
    errors = [
        "VIP: Telegram server says - Bad Request: MESSAGE_ID_INVALID",
        "FREE: Telegram server says - Bad Request: message to edit not found",
        "VIP: Telegram server says - Bad Request: chat not found",
    ]
    assert _missing_anchor_channels(errors) == {"FREE", "VIP"}
    assert _missing_anchor_channels(["VIP: Forbidden: bot is not a member"]) == set()
    assert _missing_anchor_channels([]) == set()


def test_v27_destination_contract_is_exact():
    assert _required_channels("FREE") == ["FREE"]
    assert _required_channels("VIP") == ["VIP"]
    assert _required_channels("BOTH") == ["FREE", "VIP"]


def test_v27_replacement_is_compare_and_swap_and_audited():
    src = _text("app/autotrade/telegram_anchor_guard.py")
    assert "TELEGRAM_ANCHOR_REPLACED" in src
    assert "PUBLICATION_RACE_RECONCILED" in src
    assert "CHART_REPAIR_APPLIED" in src
    assert "WHERE id=? AND {root_col}=?" in src
    assert "old_message_id" in src and "new_message_id" in src
    assert "MESSAGE_ID_INVALID".lower() in src.lower()
    assert "message to edit not found" in src


def test_v27_only_self_heals_web_admin_and_explicit_missing_message_errors():
    src = _text("app/autotrade/telegram_anchor_guard.py")
    assert '!= "WEB_ADMIN"' in src
    assert "stale_channels = _missing_anchor_channels" in src
    assert "if stale_channels:" in src
    assert "if raw:" in src
    assert "send_photo" in src
    assert "edit_message_media" not in src


def test_v27_install_order_wraps_existing_chart_guards_last():
    src = _text("app/combined_api.py")
    assert "install_chart_delivery_guard(app)" in src
    assert "install_chart_repair_claim_runtime(app)" in src
    assert "install_telegram_anchor_guard(app)" in src
    anchor_pos = src.index("install_telegram_anchor_guard(app)")
    assert src.index("install_chart_delivery_guard(app)") < anchor_pos
    assert src.index("install_chart_repair_claim_runtime(app)") < anchor_pos


def test_v27_has_no_trade_execution_side_effects():
    src = _text("app/autotrade/telegram_anchor_guard.py")
    forbidden = (
        "order_send",
        "send_order",
        "place_order",
        "MetaTrader5",
        "mt5.order",
        "autotrade_commands",
        "miniapp_execution",
    )
    for marker in forbidden:
        assert marker not in src
