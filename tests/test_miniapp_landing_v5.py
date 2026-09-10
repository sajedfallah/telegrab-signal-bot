from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "miniapp" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "miniapp" / "landing-v5.css").read_text(encoding="utf-8")
JS = (ROOT / "miniapp" / "landing-v5.js").read_text(encoding="utf-8")


def test_landing_is_rendered_before_app_shell_with_official_mark():
    landing_pos = INDEX.index('id="nexusLanding"')
    app_pos = INDEX.index('class="app-shell"')

    assert landing_pos < app_pos
    assert 'body class="landing-active"' in INDEX
    assert './assets/brand/nexus-mark.svg?v=20260910-1523' in INDEX
    assert 'class="nexus-landing-logo"' in INDEX


def test_primary_cta_is_exactly_enter_and_not_old_copy():
    assert '<button class="nexus-landing-enter" id="enterNexus" type="button">ورود</button>' in INDEX
    assert '>ورود به نکسوس</button>' not in INDEX


def test_landing_assets_are_loaded_with_fresh_cache_key():
    assert './landing-v5.css?v=20260910-1523' in INDEX
    assert './landing-v5.js?v=20260910-1523' in INDEX


def test_landing_gate_hides_app_until_user_clicks_enter():
    assert 'body.landing-active > .app-shell' in CSS
    assert "appShell.setAttribute('aria-hidden', 'true')" in JS
    assert "enterButton.addEventListener('click', enterApp, { once: true })" in JS
    assert "document.body.classList.remove('landing-active')" in JS
    assert 'landing.hidden = true' in JS


def test_landing_keeps_minimal_nexus_product_message():
    assert 'هوشمند <strong>معامله کن</strong>' in INDEX
    assert 'سیگنال‌های دقیق' in INDEX
    assert 'AutoTrade' in INDEX
    assert '>VIP<' in INDEX
    assert 'فuturistic' not in INDEX.lower()
