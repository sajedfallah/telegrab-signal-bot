from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app import db
from app.autotrade import miniapp_execution_runtime as runtime
from tests.test_miniapp_admin_signal_center import (
    ACCOUNT,
    ADMIN_ID,
    chart_headers,
    client,
    headers,
    payload,
)


def _create_online_manual_signal(client, request_id: str):
    db.ensure_admin_identity(ADMIN_ID)
    db.record_mt5_heartbeat(
        ACCOUNT,
        role="ADMIN",
        ea_version="0.6.5",
        payload={"ok": True},
    )
    response = client.post(
        "/miniapp/api/admin/signals",
        headers=headers(),
        json=payload(request_id),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_frontend_manual_publish_has_duplicate_guard_and_single_script():
    root = Path(__file__).resolve().parents[1] / "miniapp"
    html = (root / "admin.html").read_text(encoding="utf-8")
    js = (root / "admin-signal-v13.js").read_text(encoding="utf-8")

    assert html.count("admin-signal-v13.js") == 1
    assert "window.__nexusAdminSignalV13Loaded" in js
    assert "publishInFlight" in js
    assert "if (!state.preview || state.publishInFlight) return;" in js
    assert "state.publishInFlight = true;" in js
    assert "'X-Idempotency-Key': traceId" in js
    assert "button.disabled = true;" in js


def test_same_manual_request_id_creates_one_backend_signal(client):
    request_id = "manual-open-idempotent-0001"
    first = client.post(
        "/miniapp/api/admin/signals",
        headers=headers(),
        json=payload(request_id),
    )
    second = client.post(
        "/miniapp/api/admin/signals",
        headers=headers(),
        json=payload(request_id),
    )

    assert first.status_code == second.status_code == 201
    assert first.json()["signal_id"] == second.json()["signal_id"]
    assert second.json()["idempotent"] is True

    with db.conn() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM miniapp_admin_signal_requests WHERE request_id=?",
            (request_id,),
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT COUNT(*) FROM signals WHERE publish_token=?",
            (f"MINIAPP:{ADMIN_ID}:{request_id}",),
        ).fetchone()[0] == 1


def test_execution_claim_is_atomic_across_concurrent_backend_workers(client):
    created = _create_online_manual_signal(client, "manual-open-claim-0001")
    signal_id = int(created["signal_id"])

    runtime._release_execution_claim(signal_id)

    def attempt_claim(_):
        return runtime._claim_web_admin_signal(
            signal_id,
            ACCOUNT,
            "manual-open-claim-0001",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt_claim, range(8)))

    assert results.count(True) == 1
    assert results.count(False) == 7

    with db.conn() as con:
        row = con.execute(
            "SELECT request_id,account_number,claim_count "
            "FROM miniapp_admin_execution_claims WHERE signal_id=?",
            (signal_id,),
        ).fetchone()
    assert row is not None
    assert row["request_id"] == "manual-open-claim-0001"
    assert row["account_number"] == ACCOUNT
    assert int(row["claim_count"]) == 1


def test_same_pending_manual_signal_is_delivered_to_only_one_poller(client):
    created = _create_online_manual_signal(client, "manual-open-poll-0001")
    signal_id = int(created["signal_id"])

    first = client.get(
        "/api/v1/autotrade/signals?after_id=0&limit=50",
        headers=chart_headers(),
    )
    second = client.get(
        "/api/v1/autotrade/signals?after_id=0&limit=50",
        headers=chart_headers(),
    )

    assert first.status_code == second.status_code == 200
    first_items = [
        item for item in first.json()["signals"]
        if int(item["db_id"]) == signal_id
    ]
    second_items = [
        item for item in second.json()["signals"]
        if int(item["db_id"]) == signal_id
    ]

    assert len(first_items) == 1
    assert first_items[0]["request_id"] == "manual-open-poll-0001"
    assert second_items == []


def test_executed_web_admin_signal_is_never_replayed_to_new_poller(client):
    created = _create_online_manual_signal(client, "manual-open-no-replay-0001")
    signal_id = int(created["signal_id"])

    first = client.get(
        "/api/v1/autotrade/signals?after_id=0&limit=50",
        headers=chart_headers(),
    )
    assert any(int(item["db_id"]) == signal_id for item in first.json()["signals"])

    with db.conn() as con:
        now = db.now_iso()
        con.execute(
            """INSERT INTO autotrade_signal_receipts
               (signal_id,telegram_id,platform,status,first_seen_at,executed_at,ticket,error_text)
               VALUES(?,?, 'MT5','executed',?,?,?,NULL)
               ON CONFLICT(signal_id,telegram_id,platform) DO UPDATE SET
                 status='executed',executed_at=excluded.executed_at,ticket=excluded.ticket""",
            (signal_id, ADMIN_ID, now, now, "987654321"),
        )
        con.execute(
            "UPDATE signals SET status='ACTIVE',publication_stage='PUBLISHED' WHERE id=?",
            (signal_id,),
        )

    replay = client.get(
        "/api/v1/autotrade/signals?after_id=0&limit=50",
        headers=chart_headers(),
    )
    assert replay.status_code == 200
    assert all(int(item["db_id"]) != signal_id for item in replay.json()["signals"])


def test_trace_id_is_preserved_from_miniapp_to_mt5_poll(client):
    request_id = "manual-open-trace-0001"
    created = _create_online_manual_signal(client, request_id)

    polled = client.get(
        "/api/v1/autotrade/signals?after_id=0&limit=50",
        headers=chart_headers(),
    )
    assert polled.status_code == 200
    item = next(
        item for item in polled.json()["signals"]
        if int(item["db_id"]) == int(created["signal_id"])
    )
    assert item["request_id"] == request_id

    with db.conn() as con:
        events = con.execute(
            "SELECT event_type,request_id FROM signal_events "
            "WHERE signal_id=? ORDER BY id",
            (int(created["signal_id"]),),
        ).fetchall()
    assert any(
        row["event_type"] == "EXECUTION_CLAIMED"
        and row["request_id"] == request_id
        for row in events
    )
