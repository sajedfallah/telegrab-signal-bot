from __future__ import annotations

from app import db
from app import combined_api  # noqa: F401 - registers User Mini App routes
from tests.test_miniapp_admin_signal_center import client, headers


def _closed_signal(value: float, when: str, unit: str = "USD", destination: str = "FREE"):
    db.ensure_admin_identity(9001001)
    row = db.create_signal(
        market_type="GOLD", symbol="XAUUSD", direction="BUY", entry_price=3650,
        stop_loss=3645, targets=[3655], risk_percent=1, rr_ratio=1,
        destination=destination, chart_file_id=None, created_by=9001001,
    )
    db.close_signal(row["id"], 3655, value, unit, None, closed_at=when)
    return row


def test_closed_calendar_uses_close_date_and_real_usd_only(client):
    first = _closed_signal(18.4, "2026-09-10T08:00:00+00:00")
    second = _closed_signal(-7.25, "2026-09-10T18:00:00+00:00")
    _closed_signal(3.0, "2026-09-11T08:00:00+00:00", "PIPS")
    result = client.get("/miniapp/api/signals/closed-calendar?month=2026-09&day=2026-09-10", headers=headers())
    assert result.status_code == 200, result.text
    data = result.json()
    assert [item["id"] for item in data["items"]] == [first["id"], second["id"]]
    assert data["days"][0] == {"day": "2026-09-10", "count": 2, "net_pnl": 11.15, "currency": "USD"}
    assert data["days"][1]["net_pnl"] is None


def test_closed_calendar_does_not_expose_locked_vip_result(client, monkeypatch):
    from app import miniapp_signals
    monkeypatch.setattr(miniapp_signals, "PUBLIC_CLOSED_VIP_DETAILS", False)
    _closed_signal(99.0, "2026-09-10T08:00:00+00:00", destination="VIP")
    result = client.get("/miniapp/api/signals/closed-calendar?month=2026-09&day=2026-09-10", headers=headers())
    assert result.status_code == 200
    data = result.json()
    assert data["days"][0]["net_pnl"] is None
    assert data["items"][0]["locked"] is True
    assert data["items"][0]["result_value"] is None


def test_calendar_groups_by_tehran_close_date_not_creation_date(client):
    row = _closed_signal(5.0, "2026-09-10T22:00:00+00:00")
    result = client.get("/miniapp/api/signals/closed-calendar?month=2026-09&day=2026-09-11", headers=headers())
    assert result.status_code == 200
    assert result.json()["timezone"] == "Asia/Tehran"
    assert result.json()["days"][0]["day"] == "2026-09-11"
    assert result.json()["items"][0]["id"] == row["id"]
