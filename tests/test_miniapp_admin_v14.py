from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

from app import db
from app.miniapp_admin_api import CreateSignalRequest
from tests.test_miniapp_admin_signal_center import client, headers, payload


def test_risk_and_fixed_lot_contracts():
    risk = CreateSignalRequest(**payload("risk-v14-0001"), risk_percent=1.25)
    assert risk.risk_percent == 1.25 and risk.lot_size is None
    legacy = CreateSignalRequest(**payload("risk-v14-0002"))
    assert legacy.risk_percent == 1.0
    fixed = CreateSignalRequest(**(payload("fixed-v14-0001") | {"volume_mode": "FIXED", "lot_size": 0.06}))
    assert fixed.risk_percent is None and fixed.lot_size == 0.06


def test_market_quote_fails_closed_without_bid_ask(client):
    result = client.get("/miniapp/api/admin/market-quote?symbol=XAUUSD", headers=headers())
    assert result.status_code == 503
    assert "manual entry" in result.json()["detail"]


def test_market_quote_uses_fresh_authenticated_admin_bid_ask_only(client):
    now = datetime.now(timezone.utc).isoformat()
    db.record_mt5_heartbeat("80150619", role="ADMIN", payload={"quotes": {"XAUUSD": {"bid": 3650.0, "ask": 3650.2, "captured_at": now}}})
    result = client.get("/miniapp/api/admin/market-quote?symbol=XAUUSD", headers=headers())
    assert result.status_code == 200, result.text
    assert result.json()["bid"] == 3650.0 and result.json()["ask"] == 3650.2
    with db.conn() as con:
        con.execute("UPDATE mt5_heartbeats_v060 SET payload_json=? WHERE account_number=?",
                    ('{"quotes":{"XAUUSD":{"bid":3650,"ask":3650.2,"captured_at":"2020-01-01T00:00:00+00:00"}}}', "80150619"))
    stale = client.get("/miniapp/api/admin/market-quote?symbol=XAUUSD", headers=headers())
    assert stale.status_code == 503


def test_rejected_logs_clear_only_request_metadata(client):
    db.ensure_admin_identity(9001001)
    from app.miniapp_admin_api import init_miniapp_admin_schema
    init_miniapp_admin_schema()
    signal = db.create_signal(
        market_type="GOLD", symbol="XAUUSD", direction="BUY", entry_price=3650,
        stop_loss=3645, targets=[3655, 3657.5, 3660, 3665], risk_percent=1,
        rr_ratio=3, destination="BOTH", chart_file_id=None, created_by=9001001,
    )
    with db.conn() as con:
        for request_id, status in (("rejected-0001", "REJECTED"), ("pending-0002", "READY")):
            con.execute(
                "INSERT INTO miniapp_admin_signal_requests(request_id,admin_telegram_id,signal_id,status,payload_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (request_id, 9001001, signal["id"], status, "{}", db.now_iso(), db.now_iso()),
            )
    listed = client.get("/miniapp/api/admin/rejected-logs", headers=headers())
    assert listed.status_code == 200
    assert [row["request_id"] for row in listed.json()["items"]] == ["rejected-0001"]
    cleared = client.delete("/miniapp/api/admin/rejected-logs", headers=headers())
    assert cleared.status_code == 200 and cleared.json()["deleted"] == 1
    assert db.get_signal(signal["id"]) is not None
    with db.conn() as con:
        assert con.execute("SELECT COUNT(*) FROM miniapp_admin_signal_requests WHERE status='READY'").fetchone()[0] == 1


def test_v14_ui_contract():
    root = Path(__file__).resolve().parents[1] / "miniapp"
    html = (root / "admin.html").read_text(encoding="utf-8")
    js = (root / "admin-signal-v13.js").read_text(encoding="utf-8")
    assert "admin-light-v14.css" in html
    assert 'list="adminSymbols"' in html
    assert "riskPercentLabel" in html and "autoRiskPercentLabel" in html
    assert "quote.ask : quote.bid" in js
    assert "!quote.fresh" in js
    assert "confirm('فقط درخواست‌های ردشده" in js
    assert '<details class="admin-action-sheet">' in js
    assert 'Open Positions' in js and 'Pending Orders' in js
    assert "rawProfit == null ? '—'" in js


def test_symbol_visuals_are_shared_and_broker_symbol_is_not_rewritten():
    root = Path(__file__).resolve().parents[1] / "miniapp"
    visuals = (root / "symbol-visuals.js").read_text(encoding="utf-8")
    user = (root / "signals-v2.js").read_text(encoding="utf-8")
    admin = (root / "admin-signal-v13.js").read_text(encoding="utf-8")
    assert "window.NexusSymbolVisuals" in visuals
    assert "window.NexusSymbolVisuals" in user and "window.NexusSymbolVisuals" in admin
    assert "BTC:" in visuals and "XAU:" in visuals and "US30:" in visuals
    assert "normalize_symbol" not in visuals
