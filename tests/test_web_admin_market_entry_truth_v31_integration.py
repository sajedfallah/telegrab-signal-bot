from __future__ import annotations

from datetime import datetime, timezone

import app.combined_api  # Install the Production runtime stack in this fresh pytest process.
from app import db
from tests.test_miniapp_admin_signal_center import ACCOUNT, client, headers, payload


def _record_quote(*, bid: float, ask: float) -> None:
    db.ensure_admin_identity(9001001)
    db.record_mt5_heartbeat(
        ACCOUNT,
        role="ADMIN",
        ea_version="0.6.5",
        payload={
            "quotes": {
                "XAUUSD": {
                    "bid": bid,
                    "ask": ask,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                }
            }
        },
    )


def test_v31_final_route_accepts_fresh_market_aligned_entry(client):
    _record_quote(bid=3650.0, ask=3650.2)
    body = payload("v31-aligned-entry")
    body["entry"] = 3650.2
    body["stop_loss"] = 3645.0
    response = client.post("/miniapp/api/admin/signals", headers=headers(), json=body)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["entry_truth"]["status"] == "VALIDATED_FRESH_MT5_QUOTE"
    assert result["entry_truth"]["ok"] is True
    assert result["status"] == "WAITING_EXECUTION"


def test_v31_final_route_rejects_nx55_scale_fresh_quote_drift_before_signal_row(client):
    _record_quote(bid=4283.50, ask=4283.70)
    body = payload("v31-reject-stale-entry")
    body.update({"direction": "SELL", "entry": 4291.0, "stop_loss": 4296.0})
    response = client.post("/miniapp/api/admin/signals", headers=headers(), json=body)
    assert response.status_code == 409, response.text
    assert "Refresh Market Price and publish again" in response.json()["detail"]
    with db.conn() as con:
        assert con.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM miniapp_admin_signal_requests").fetchone()[0] == 0


def test_v31_final_route_preserves_offline_queue_without_inventing_quote(client):
    body = payload("v31-offline-deferred")
    response = client.post("/miniapp/api/admin/signals", headers=headers(), json=body)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["entry_truth"]["status"] == "DEFERRED_NO_FRESH_QUOTE"
    assert result["entry_truth"]["deferred"] is True
    assert result["status"] == "WAITING_FOR_MT5"
    assert result["chart_job"] is None
