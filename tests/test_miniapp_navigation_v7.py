from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "miniapp" / "index.html").read_text(encoding="utf-8")
NAV_JS = (ROOT / "miniapp" / "navigation-v7.js").read_text(encoding="utf-8")
NAV_CSS = (ROOT / "miniapp" / "navigation-v7.css").read_text(encoding="utf-8")
LANDING_JS = (ROOT / "miniapp" / "landing-v5.js").read_text(encoding="utf-8")


def test_visible_back_button_is_part_of_global_topbar():
    assert 'id="nexusBackBtn"' in INDEX
    assert 'class="nexus-page-back"' in INDEX
    assert 'بازگشت' in INDEX
    assert './navigation-v7.css?v=20260910-1845' in INDEX
    assert './navigation-v7.js?v=20260910-1845' in INDEX


def test_back_navigation_tracks_previous_routes_and_custom_views():
    assert "const routeStack = ['landing']" in NAV_JS
    assert "routeStack.push(currentRoute)" in NAV_JS
    assert "window.NexusTrackRecord?.open" in NAV_JS
    assert "window.NexusTrades?.open" in NAV_JS
    assert "render(route)" in NAV_JS
    assert "function goBack()" in NAV_JS


def test_home_back_returns_to_landing_using_shared_lifecycle():
    assert "currentRoute === 'home' ? 'landing' : 'home'" in NAV_JS
    assert "window.NexusLanding.show()" in NAV_JS
    assert "window.NexusLanding =" in LANDING_JS
    assert "show: showLanding" in LANDING_JS


def test_modal_back_closes_modal_before_route_navigation():
    assert "if (modalVisible())" in NAV_JS
    assert "closeModal()" in NAV_JS


def test_home_primary_cta_is_renamed_to_analysis_room_at_runtime():
    assert ".home-v2-actions [data-enter-nexus] span" in NAV_JS
    assert "label.textContent = 'اتاق تحلیل'" in NAV_JS


def test_back_control_has_mobile_safe_styles_and_is_hidden_on_landing():
    assert ".nexus-page-back" in NAV_CSS
    assert "body.landing-active .nexus-page-back" in NAV_CSS
    assert "@media (max-width: 380px)" in NAV_CSS
