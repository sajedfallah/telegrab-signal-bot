import base64
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "miniapp" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "miniapp" / "landing-v5.css").read_text(encoding="utf-8")
JS = (ROOT / "miniapp" / "landing-v5.js").read_text(encoding="utf-8")
POSTER = ROOT / "miniapp" / "assets" / "brand" / "nexus-landing-minimal-v9.svg"


def test_landing_is_rendered_before_app_shell_with_approved_poster():
    landing_pos = INDEX.index('id="nexusLanding"')
    app_pos = INDEX.index('class="app-shell"')

    assert landing_pos < app_pos
    assert 'body class="landing-active"' in INDEX
    assert 'class="nexus-landing-poster"' in INDEX
    assert './assets/brand/nexus-landing-minimal-v9.svg?v=20260911-0340' in INDEX
    assert 'fetchpriority="high"' in INDEX


def test_approved_poster_asset_is_embedded_webp_svg_and_reasonably_optimized():
    payload = POSTER.read_text(encoding="utf-8")
    raw = POSTER.read_bytes()

    assert 20_000 < len(raw) < 150_000
    assert payload.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    assert 'width="480" height="852"' in payload
    match = re.search(r'data:image/webp;base64,([^\"]+)', payload)
    assert match is not None
    image = base64.b64decode(match.group(1))
    assert image.startswith(b"RIFF")
    assert image[8:12] == b"WEBP"


def test_primary_cta_remains_native_click_target_with_exact_accessible_copy():
    assert 'class="nexus-landing-enter" id="enterNexus" type="button" aria-label="ورود"' in INDEX
    assert '<span class="nexus-visually-hidden">ورود</span>' in INDEX
    assert 'ورود به نکسوس' not in INDEX


def test_landing_uses_poster_first_full_viewport_layout():
    assert '.nexus-landing-poster-frame' in CSS
    assert 'object-fit: cover' in CSS
    assert '.nexus-landing-enter' in CSS
    assert 'background: transparent' in CSS
    assert 'body.landing-active > .app-shell' in CSS
    assert './landing-v5.css?v=20260910-1731' in INDEX


def test_landing_gate_hides_app_until_user_clicks_enter():
    assert "appShell.setAttribute('aria-hidden', 'true')" in JS
    assert "enterButton.addEventListener('click', enterApp)" in JS
    assert "{ once: true }" not in JS
    assert "document.body.classList.remove('landing-active')" in JS
    assert 'landing.hidden = true' in JS


def test_landing_resets_for_every_reopen_without_persisted_bypass():
    assert 'const showLanding = () =>' in JS
    assert "document.addEventListener('visibilitychange'" in JS
    assert "document.visibilityState === 'hidden'" in JS
    assert "window.addEventListener('pagehide', resetForNextOpen)" in JS
    assert "window.addEventListener('pageshow', showLanding)" in JS
    assert 'sessionStorage' not in JS
    assert 'localStorage' not in JS
