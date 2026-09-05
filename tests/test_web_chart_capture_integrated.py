from pathlib import Path
from types import SimpleNamespace

from app import db
from app import web_chart_capture_runtime as capture


def _payload():
    return {
        "market_type": "GOLD",
        "symbol": "XAUUSD",
        "direction": "BUY",
        "timeframe": "M5",
        "order_type": "MARKET",
        "entry_price": 2400.0,
        "stop_loss": 2390.0,
        "targets": [2410.0, 2420.0, 2430.0],
        "risk_percent": 1.0,
        "rr_ratio": None,
        "destination": "BOTH",
        "volume_mode": "RISK",
        "lot_size": None,
        "leverage": None,
        "trailing_code": "NEXUS_TRAIL_07",
        "trailing_name": None,
        "max_entry_deviation_pct": None,
        "max_entry_deviation_abs": None,
        "stop_limit_price": None,
    }


def test_web_signal_request_is_idempotent_and_does_not_reset_publication(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "nexus.db")
    monkeypatch.setattr(
        capture,
        "settings",
        SimpleNamespace(nexus_admin_mt5_accounts=("70001",)),
    )
    db.init_db()
    db.upsert_user(1, "admin", "Admin")
    capture.ensure_schema()

    first = capture.create_web_signal(
        payload=_payload(), admin_id=1, issuer_account="70001", request_id="WEB-IDEMPOTENT-001"
    )
    assert first["status"] == "DRAFT"
    state = capture.publication_status(int(first["id"]))
    assert state["publication"]["stage"] == "WAITING_FOR_CHART"
    assert state["job"]["status"] == "PENDING"

    with db.conn() as con:
        con.execute(
            "UPDATE web_signal_publications SET stage='PUBLISHED' WHERE signal_id=?",
            (int(first["id"]),),
        )

    second = capture.create_web_signal(
        payload=_payload(), admin_id=1, issuer_account="70001", request_id="WEB-IDEMPOTENT-001"
    )
    assert int(second["id"]) == int(first["id"])
    assert second["publication_stage"] == "PUBLISHED"
    with db.conn() as con:
        count = con.execute(
            "SELECT COUNT(*) FROM signal_chart_capture_jobs WHERE signal_id=?",
            (int(first["id"]),),
        ).fetchone()[0]
    assert count == 1


def test_web_signal_is_not_distributed_before_publication(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "nexus.db")
    monkeypatch.setattr(capture, "settings", SimpleNamespace(nexus_admin_mt5_accounts=("70001",)))
    db.init_db()
    db.upsert_user(1, "admin", "Admin")
    capture.ensure_schema()
    capture._patch_active_signals()

    row = capture.create_web_signal(
        payload=_payload(), admin_id=1, issuer_account="70001", request_id="WEB-GATE-001"
    )
    assert not any(int(x["id"]) == int(row["id"]) for x in db.autotrade_active_signals())

    with db.conn() as con:
        con.execute("UPDATE signals SET status='ACTIVE' WHERE id=?", (int(row["id"]),))
    assert any(int(x["id"]) == int(row["id"]) for x in db.autotrade_active_signals())


def test_chart_agent_is_screenshot_only_and_uses_dedicated_chart():
    src = Path("mt5/NEXUS_ChartAgent/NEXUS_ChartAgent.mq5").read_text(encoding="utf-8-sig")
    assert "/api/v1/autotrade/admin/chart-capture/next" in src
    assert "/result" in src
    assert "ChartOpen(" in src
    assert "ChartScreenShot(" in src
    assert "NXS.SHOT." in src
    assert "void OnTick()" in src
    assert "screenshot-only and never trades" in src
    for forbidden in ("OrderSend(", "PositionOpen(", "Buy(", "Sell("):
        assert forbidden not in src


def test_web_admin_requires_review_before_issue():
    src = Path("admin-web/dist/signal.js").read_text(encoding="utf-8-sig")
    assert "REVIEW SIGNAL" in src
    assert "ISSUE SIGNAL" in src
    assert "/signals/issue" in src
    assert "/chart-agents" in src
    assert "MT5 Screenshot Agent آفلاین است" in src
