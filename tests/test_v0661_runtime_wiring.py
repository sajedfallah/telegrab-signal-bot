from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_API = (ROOT / "run_api.py").read_text(encoding="utf-8-sig")
CLEANUP = (ROOT / "app/autotrade_cleanup_runtime.py").read_text(encoding="utf-8-sig")


def test_api_installs_reconcile_guard_before_fastapi_import():
    guard_import = RUN_API.index(
        "from app.autotrade.notification_queue_guard import install_notification_queue_guard"
    )
    guard_call = RUN_API.index("install_notification_queue_guard()")
    app_import = RUN_API.index("from app.combined_api import app")
    assert guard_import < guard_call < app_import


def test_bot_notification_runtime_installs_reconcile_guard_and_lifecycle_truth():
    assert ".autotrade.notification_queue_guard import install_notification_queue_guard" in CLEANUP
    assert "install_notification_queue_guard()" in CLEANUP
    assert ".autotrade.telegram_lifecycle_truth import install_telegram_lifecycle_truth" in CLEANUP
    assert "install_telegram_lifecycle_truth(core)" in CLEANUP
