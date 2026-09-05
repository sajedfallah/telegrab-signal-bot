from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8-sig")


def test_miniapp_has_no_signal_issue_endpoint_or_issue_function():
    api = _read("app/miniapp_api.py")
    forbidden = (
        '@router.post("/admin/signals"',
        "create_admin_signal(",
        "issue_mt5_admin_signal(",
        "create_signal(",
    )
    for marker in forbidden:
        assert marker not in api
    assert '"signal_issue": False' in api
    assert '"signal_publish": False' in api


def test_miniapp_risk_uses_production_firewall_not_parallel_preferences():
    api = _read("app/miniapp_api.py")
    assert "from .autotrade import risk_firewall" in api
    assert "risk_firewall.set_user_profile" in api
    assert "risk_firewall.global_kill_switch" in api
    assert "user_risk_preferences" not in api


def test_miniapp_dev_bypass_is_fail_closed_in_production():
    api = _read("app/miniapp_api.py")
    assert "Mini App development bypass is forbidden in production" in api
    assert 'env not in {"dev", "development", "test"}' in api


def test_bot_keeps_public_entry_first_and_inserts_miniapp_after_it():
    runtime = _read("app/miniapp_bot_runtime.py")
    assert "insert_at = 1 if markup.inline_keyboard else 0" in runtime
    assert "WebAppInfo(url=url)" in runtime
    run = _read("run.py")
    assert "install_customer_menu_runtime(main_module)" in run
    assert "install_miniapp_bot_runtime(main_module)" in run
    assert run.index("install_customer_menu_runtime(main_module)") < run.index("install_miniapp_bot_runtime(main_module)")


def test_api_mounts_web_and_miniapp_after_production_hardening():
    run = _read("run_api.py")
    assert "install_risk_firewall()" in run
    assert "install_live_snapshot_event_bridge()" in run
    assert "install_admin_web_runtime()" in run
    assert "install_miniapp_runtime()" in run
    assert run.index("install_risk_firewall()") < run.index("install_admin_web_runtime()")
    assert run.index("install_live_snapshot_event_bridge()") < run.index("install_miniapp_runtime()")
