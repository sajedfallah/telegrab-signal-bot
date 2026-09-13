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


def _close_receipt(signal_id: int, profit: float, event_id: str):
    with db.conn() as con:
        con.execute(
            "INSERT INTO autotrade_trade_executions "
            "(telegram_id,signal_id,ticket,event_id,event_type,profit,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (9001001, signal_id, "ticket-1", event_id, "CLOSE", profit, db.now_iso(), db.now_iso()),
        )


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


def test_closed_calendar_prefers_broker_close_and_sums_partial_closes(client):
    row = _closed_signal(999.0, "2026-09-10T08:00:00+00:00")
    _close_receipt(row["id"], 12.5, "partial-1")
    _close_receipt(row["id"], -2.25, "partial-2")
    result = client.get("/miniapp/api/signals/closed-calendar?month=2026-09&day=2026-09-10", headers=headers())
    assert result.status_code == 200, result.text
    assert result.json()["days"][0]["net_pnl"] == 10.25
    assert result.json()["items"][0]["realized_pnl"] == 10.25


def test_closed_calendar_missing_item_does_not_erase_known_daily_pnl(client):
    _closed_signal(8.0, "2026-09-10T08:00:00+00:00")
    _closed_signal(3.0, "2026-09-10T09:00:00+00:00", "PIPS")
    result = client.get("/miniapp/api/signals/closed-calendar?month=2026-09&day=2026-09-10", headers=headers())
    assert result.status_code == 200
    assert result.json()["days"][0]["net_pnl"] == 8.0
    assert [item["realized_pnl"] for item in result.json()["items"]] == [8.0, None]


def test_closed_calendar_does_not_expose_vip_broker_receipt(client, monkeypatch):
    from app import miniapp_signals
    monkeypatch.setattr(miniapp_signals, "PUBLIC_CLOSED_VIP_DETAILS", False)
    row = _closed_signal(99.0, "2026-09-10T08:00:00+00:00", destination="VIP")
    _close_receipt(row["id"], 123.0, "vip-close")
    result = client.get("/miniapp/api/signals/closed-calendar?month=2026-09&day=2026-09-10", headers=headers())
    assert result.status_code == 200
    assert result.json()["days"][0]["net_pnl"] is None
    assert result.json()["items"][0]["realized_pnl"] is None
    assert result.json()["items"][0]["result_label_fa"] is None


def test_closed_calendar_does_not_mix_another_customers_execution(client):
    row = _closed_signal(4.0, "2026-09-10T08:00:00+00:00")
    db.upsert_user(9001002, "other", "Other")
    with db.conn() as con:
        con.execute(
            "INSERT INTO autotrade_trade_executions "
            "(telegram_id,signal_id,ticket,event_id,event_type,profit,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (9001002, row["id"], "other-ticket", "other-close", "CLOSE", 500.0, db.now_iso(), db.now_iso()),
        )
    result = client.get("/miniapp/api/signals/closed-calendar?month=2026-09&day=2026-09-10", headers=headers())
    assert result.status_code == 200
    assert result.json()["items"][0]["realized_pnl"] == 4.0
