from pathlib import Path


MINIAPP = Path(__file__).resolve().parents[1] / "miniapp"


def test_home_uses_explicit_trust_to_vip_story_without_operational_dashboard():
    home = (MINIAPP / "home-v2.js").read_text(encoding="utf-8")
    order = home.split("function normalizedOrder(payload)", 1)[1].split("async function switchPerformance", 1)[0]
    assert "['spotlight', 'performance', 'recent_signals', 'vip_conversion'," in order
    assert "'community', 'autotrade_teaser']" in order
    for unwanted in ("'today'", "'autotrade_health'", "'trades_preview'", "'subscription'", "'offer'"):
        assert unwanted not in order
    assert "data-home-go=\"performance\"" in home
    assert "data-home-go=\"signals\"" in home
    assert "data-home-go=\"subscriptions\"" not in order


def test_vip_preview_stays_after_recent_signal_evidence():
    preview = (MINIAPP / "vip-preview-v1.js").read_text(encoding="utf-8")
    assert "host.querySelector('.home-v066-vip')" in preview
    assert "host.insertBefore(node, conversion)" in preview
    assert "api('/vip-preview')" in preview
    assert "item.symbol" in preview
    assert "item.entry_price" not in preview
    assert "item.stop_loss" not in preview


def test_final_user_layer_is_scoped_and_landing_is_packaged():
    html = (MINIAPP / "index.html").read_text(encoding="utf-8")
    css = (MINIAPP / "user-v066-final.css").read_text(encoding="utf-8")
    poster = MINIAPP / "assets" / "brand" / "nexus-landing-approved-final.webp"
    assert './user-v066-final.css?v=20260914-next-ui' in html
    assert './assets/brand/nexus-landing-approved-final.webp?v=' in html
    assert poster.read_bytes()[:4] == b"RIFF"
    assert ".app-shell" in css
    assert ".admin" not in css
    assert "@import" not in css
    assert "user-final-polish-v1.js" not in html
    assert "signal-card-runtime-v5.css" not in html
