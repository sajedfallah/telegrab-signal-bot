from pathlib import Path


MINIAPP = Path(__file__).resolve().parents[1] / "miniapp"


def test_home_and_signals_do_not_silently_keep_initial_templates_without_auth():
    app = (MINIAPP / "app.js").read_text(encoding="utf-8")
    home = (MINIAPP / "home-v2.js").read_text(encoding="utf-8")
    signals = (MINIAPP / "signals-v2.js").read_text(encoding="utf-8")

    assert "function renderAuthUnavailable()" in app
    assert "retryNexusBootstrap" in app
    assert "window.setTimeout(() => bootstrap(false), 250)" in app
    assert "if (bootstrapUnavailable) renderAuthUnavailable()" in app
    assert "renderAuthUnavailable();" in home
    assert "renderAuthUnavailable();" in signals
    assert "window.Telegram?.WebApp?.initData" in home
    assert "window.Telegram?.WebApp?.initData" in signals


def test_bootstrap_dispatches_to_real_home_and_signals_hydrators():
    app = (MINIAPP / "app.js").read_text(encoding="utf-8")
    home = (MINIAPP / "home-v2.js").read_text(encoding="utf-8")
    signals = (MINIAPP / "signals-v2.js").read_text(encoding="utf-8")

    assert "if (state.route === 'home') window.hydrateNexusHome?.();" in app
    assert "if (window.hydrateNexusSignals) window.hydrateNexusSignals();" in app
    assert "const payload = await api('/home')" in home
    assert "view.innerHTML = `<div class=\"home-v2\">" in home
    assert "const data = await api(`/signals?${query}`)" in signals
    assert "feed.innerHTML = html" in signals
    assert "retrySignals" in signals


def test_telegram_auth_header_is_read_at_request_time():
    app = (MINIAPP / "app.js").read_text(encoding="utf-8")
    assert "const telegramWebApp = () => window.Telegram?.WebApp" in app
    assert "const initData = telegramWebApp()?.initData || ''" in app
    assert "'X-Telegram-Init-Data': initData" in app
