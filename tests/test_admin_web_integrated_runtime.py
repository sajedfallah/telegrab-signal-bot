from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8-sig")


def test_run_api_preserves_production_runtimes_before_web_mount():
    src = _read("run_api.py")
    assert "install_free_topic_routing()" in src
    assert "install_two_digit_signal_codes()" in src
    assert "install_risk_firewall()" in src
    assert "install_live_snapshot_event_bridge()" in src
    assert "install_admin_web_runtime()" in src
    assert src.index("install_risk_firewall()") < src.index("install_admin_web_runtime()")
    assert src.index("install_live_snapshot_event_bridge()") < src.index("install_admin_web_runtime()")


def test_web_api_uses_existing_risk_firewall_as_single_source_of_truth():
    src = _read("app/admin_api.py")
    assert "from .autotrade import risk_firewall" in src
    assert "risk_firewall.set_global_kill_switch" in src
    assert "risk_firewall.set_user_profile" in src
    # The integrated web layer must not recreate the old parallel risk schema.
    assert "CREATE TABLE IF NOT EXISTS expert_settings" not in src
    assert "CREATE TABLE IF NOT EXISTS user_risk_preferences" not in src
    assert "CREATE TABLE IF NOT EXISTS system_controls" not in src
    assert "CREATE TABLE IF NOT EXISTS risk_policies" not in src


def test_admin_and_portal_tokens_are_scope_separated():
    src = _read("app/admin_api.py")
    assert 'expected_scope="admin"' in src
    assert 'expected_scope="portal"' in src
    assert 'scope="admin"' in src
    assert 'scope="portal"' in src


def test_signal_authority_contract_excludes_miniapp():
    src = _read("app/admin_api.py")
    assert '"signal_authorities": ["MT5_ADMIN", "WEB_ADMIN"]' in src
    assert '"miniapp_signal_issuance": False' in src


def test_web_signal_options_require_real_chart_capture_before_enablement():
    src = _read("app/admin_api.py")
    assert '"chart_capture_required": True' in src
    assert 'web_mt5_chart_capture_enabled' in src
