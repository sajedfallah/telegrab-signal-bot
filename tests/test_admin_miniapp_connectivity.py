from pathlib import Path

def test_combined_api_registers_admin_routes():
    from app.combined_api import app
    paths = {getattr(route, "path", "") for route in app.routes}
    required = {
        "/miniapp/api/admin/health",
        "/miniapp/api/admin/bootstrap",
        "/miniapp/api/admin/signals",
        "/miniapp/api/admin/signals/calculate",
        "/miniapp/api/admin/active-signals",
        "/miniapp/api/admin/rejected-logs",
        "/miniapp/api/admin/positions",
    }
    assert required <= paths

def test_admin_frontend_uses_relative_api_and_telegram_init_data_only():
    js = Path("miniapp/admin-signal-v13.js").read_text(encoding="utf-8")
    assert "const API = '/miniapp/api/admin'" in js
    assert "X-Telegram-Init-Data" in js
    assert "X-NEXUS-Admin-Token" not in js
    assert "127.0.0.1" not in js
    assert "localhost" not in js
