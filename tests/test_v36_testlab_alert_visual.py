from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def test_alert_dedup_is_durable_and_incident_keyed():
    src = text("app/autotrade/chart_alert_dedup_runtime.py")
    assert "CREATE TABLE IF NOT EXISTS chart_delivery_alert_incidents" in src
    assert "incident_key TEXT PRIMARY KEY" in src
    assert "INSERT OR IGNORE INTO chart_delivery_alert_incidents" in src
    assert "guard._alert_due = durable_alert_due" in src
    assert '"signal_id": signal_id' in src
    assert '"job_id": int(first.get("job_id"))' in src
    assert '"error": str(first.get("error_text")' in src


def test_combined_api_installs_dedup_after_guard_and_testlab_after_v34():
    src = text("app/combined_api.py")
    assert src.index("install_chart_delivery_guard(app)") < src.index("install_chart_alert_dedup_runtime(app)")
    assert src.index("install_publication_consistency(app)") < src.index("install_test_lab_runtime(app)")


def test_test_lab_is_explicit_env_bound_and_forces_single_test_destination():
    src = text("app/autotrade/test_lab_runtime.py")
    assert 'NEXUS_TEST_MT5_ACCOUNT' in src
    assert 'NEXUS_TEST_CHANNEL_ID' in src
    assert 'request_id.upper().startswith("TEST:")' in src
    assert 'req.destination = "FREE"' in src
    assert 'account != test_account' in src
    assert 'con.execute("UPDATE signals SET destination=\'NONE\'' in src
    assert 'req.destination = "NONE"' in src


def test_demo_expert_refuses_non_demo_accounts_and_reuses_production_core():
    src = text("mt5/NEXUS_AutoTrade_UI65/NEXUS_AutoTrade_Demo.mq5")
    assert '#include "Core/NEXUS_AutoTrade_Core.mq5"' in src
    assert '#define OnInit NEXUS_Demo_Core_OnInit' in src
    assert 'ACCOUNT_TRADE_MODE_DEMO' in src
    assert 'return NEXUS_Demo_Core_OnInit();' in src


def test_test_miniapp_marks_requests_with_test_prefix_and_fixed_lot_default():
    src = text("miniapp/admin-test.html")
    assert "NEXUS Test Lab" in src
    assert "TEST CHANNEL" in src
    assert "'TEST:'+Date.now()" in src
    assert 'value="0.02"' in src
    assert "NEXUS_TRAIL_07" in src


def test_visual_patch_removes_solid_boxes_and_makes_price_readable():
    src = text("tools/apply_chart_visual_v36.ps1")
    assert 'clean-text-level-v36' in src
    assert "OBJ_RECTANGLE_LABEL" in src  # verifier rejects it inside DrawCompactTag
    assert 'OBJPROP_COLOR,clrWhite' in src
    assert 'Arial Bold' in src
    assert 'MathMax(edge,MathMin(output_height-edge,center_y))' in src
    assert 'CHART VISUAL V36 PATCH: PASS' in src
