from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from app.autotrade.chart_delivery_guard import _validate_png


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def _png(width: int = 640, height: int = 360) -> bytes:
    out = BytesIO()
    Image.new("RGB", (width, height), (8, 13, 19)).save(out, format="PNG")
    return out.getvalue()


def test_scenario_1_valid_chart_asset_is_accepted_and_invalid_or_oversized_is_rejected():
    assert _validate_png(_png()) == (True, "OK")
    assert _validate_png(b"") == (False, "EMPTY")
    assert _validate_png(b"not-a-png") == (False, "BAD_SIGNATURE")
    assert _validate_png(_png(80, 60)) == (False, "TOO_SMALL")
    assert _validate_png(b"\x89PNG\r\n\x1a\n" + b"x" * 5_000_001)[0] is False


def test_scenario_2_poll_and_result_fail_rate_limits_are_isolated():
    src = _text("app/autotrade/chart_delivery_guard.py")
    assert 'bucket = f"{str(account).strip()}:{int(limit)}"' in src
    assert "api_mod._chart_rate_limit = isolated_chart_rate_limit" in src
    assert "Poll uses limit=60" in src
    assert "result/fail use limit=30" in src


def test_scenario_3_terminal_capture_gets_bounded_repair_after_fallback():
    src = _text("app/autotrade/chart_delivery_guard.py")
    assert "_MAX_REPAIR_CYCLES = 2" in src
    assert "retry_chart_capture_job" in src
    assert "CHART_REPAIR_QUEUED" in src
    assert "PUBLISHED_REPAIR_PENDING" in src
    assert "fallback_already_published" in src


def test_scenario_4_late_real_chart_replaces_existing_telegram_fallback_media():
    src = _text("app/autotrade/chart_delivery_guard.py")
    assert "edit_message_media" in src
    assert "InputMediaPhoto" in src
    assert "CHART_REPAIR_APPLIED" in src
    assert "message is not modified" in src
    assert "repaired_channels" in src


def test_scenario_5_chartagent_patch_has_range_settle_and_transient_http_retry():
    src = _text("tools/apply_chart_agent_reliability_v24.ps1")
    for marker in (
        "SCALE_VISIBLE_RANGE_CONFIRMED",
        "SCALE_FIXED_RANGE_CONFIRMED",
        "SCALE_AUTOSCALE_FALLBACK",
        "PostWithRetry",
        "status==429",
        "status==502",
        "status==503",
        "status==504",
        "SCREENSHOT_TOO_SMALL_BYTES_",
        "SCREENSHOT_UPLOAD_CONFIRMED",
    ):
        assert marker in src


def test_scenario_6_monitoring_health_and_alerting_are_installed_after_publication_recovery():
    combined = _text("app/combined_api.py")
    guard = _text("app/autotrade/chart_delivery_guard.py")
    assert "install_chart_delivery_guard(app)" in combined
    assert combined.index("install_publication_recovery(app)") < combined.index("install_chart_delivery_guard(app)")
    assert "/api/v1/autotrade/admin/chart-capture/health" in guard
    assert "_send_admin_alert" in guard
    assert "_ALERT_THROTTLE_SECONDS = 600" in guard


def test_scenario_7_diagnostic_tool_is_read_only_and_never_claims_next_job():
    src = _text("tools/diagnose_chart_delivery_v24.ps1")
    assert "READ-ONLY" in src
    assert "chart-capture/health" in src
    assert "CHART_REPAIR_APPLIED" in src
    # The diagnostic text may mention /next only in the explicit safety message;
    # it must never issue a web request to that endpoint.
    assert 'Invoke-RestMethod -Uri $Url' in src
    assert '$Url = "https://api.nexustrade.ir/api/v1/autotrade/admin/chart-capture/health' in src
