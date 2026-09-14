from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "provider_panel"


def test_provider_panel_files_exist():
    for name in ("index.html", "styles.css", "app.js", "README.md"):
        assert (PANEL / name).is_file(), name


def test_approved_visual_components_are_present():
    html = (PANEL / "index.html").read_text(encoding="utf-8")
    required = (
        "Active Subscribers",
        "Monthly Revenue",
        "Total Signals",
        "Win Rate",
        'id="revenueChart"',
        'id="signalDonut"',
        "Recent Signals",
        "Quick Actions",
        "Signal Center",
        "Copy Trade",
        "Subscribers",
        "Reports & Analytics",
        "Settings & Branding",
        "Telegram",
        "MT5",
    )
    for marker in required:
        assert marker in html, marker


def test_live_dashboard_hydration_preserves_preview_contract():
    js = (PANEL / "app.js").read_text(encoding="utf-8")
    required = (
        "/provider/api/bootstrap",
        "/provider/api/subscribers",
        "/provider/api/revenue",
        "X-Telegram-Init-Data",
        "X-Tenant-Id",
        "dashboard.health",
        "health.recovery",
        "recent_signals",
        "signal_distribution",
        "active_subscribers",
        "applySubscribersLive",
        "applyRevenueLive",
        "subscriberTable",
        "Live settled revenue",
        "Preview data retained",
    )
    for marker in required:
        assert marker in js, marker


def test_existing_customer_miniapp_is_not_replaced():
    assert (ROOT / "miniapp" / "index.html").is_file()
    assert PANEL != ROOT / "miniapp"
