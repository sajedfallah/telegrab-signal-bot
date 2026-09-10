from pathlib import Path

from app.miniapp_runtime import _plans, _telegram_user


ROOT = Path(__file__).resolve().parent.parent


def test_plans_keep_approved_subscription_periods(monkeypatch):
    monkeypatch.setenv("PLAN_30_PRICE", "30")
    monkeypatch.setenv("PLAN_90_PRICE", "90")
    monkeypatch.setenv("PLAN_180_PRICE", "180")
    plans = _plans()
    assert [p["code"] for p in plans] == ["30", "90", "180"]
    assert plans[0]["title"] == "VIP 30 روزه"


def test_invalid_telegram_init_data_is_rejected():
    assert _telegram_user("auth_date=1&hash=bad", "token") is None


def test_miniapp_exposes_persistent_actions():
    html = (ROOT / "miniapp" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "miniapp" / "app.js").read_text(encoding="utf-8")

    assert 'class="bottom-nav"' in html
    for route in ("home", "signals", "subscriptions", "account"):
        assert f'data-route="{route}"' in html
    assert "document.querySelectorAll('.nav-item')" in js
