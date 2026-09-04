from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_durable_cleanup_is_installed_and_restart_safe():
    run_py = (ROOT / "run.py").read_text(encoding="utf-8")
    source = (ROOT / "app" / "autotrade_cleanup_runtime.py").read_text(encoding="utf-8")
    assert "install_autotrade_durable_cleanup(core_main)" in run_py
    assert "deleted_at" in source
    assert "autotrade_user_event_deliveries" in source
    assert "autotrade_notification_ttl_seconds" in source
    assert "await bot.delete_message" in source
    assert "worker_with_cleanup" in source
