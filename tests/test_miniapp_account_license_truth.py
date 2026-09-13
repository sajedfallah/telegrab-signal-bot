from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import db, miniapp_account


def test_account_separates_active_cancelled_and_expired_licenses(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "account-license-test.db")
    db.init_db()
    uid = 771234
    db.upsert_user(uid, "license_test", "License")
    now = datetime.now(timezone.utc)
    past = (now - timedelta(days=3)).isoformat()
    future = (now + timedelta(days=30)).isoformat()
    with db.conn() as con:
        for status, expiry in (("active", future), ("cancelled", future), ("expired", past)):
            con.execute(
                """INSERT INTO licenses
                   (telegram_id,plan_code,vip_access,autotrade_access,starts_at,expires_at,
                    vip_expires_at,autotrade_expires_at,status,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (uid, "VIP1M", 1, 0, past, expiry, expiry, None, status, past),
            )
    monkeypatch.setattr(miniapp_account, "_entitlements", lambda _: {"vip": False, "autotrade": False})
    monkeypatch.setattr(miniapp_account, "_autotrade_customer_state", lambda *_: {})
    result = miniapp_account.build_account_status(uid)
    assert len(result["licenses"]["active"]) == 1
    assert result["licenses"]["active"][0]["display_status"] == "ACTIVE"
    assert {row["display_status"] for row in result["licenses"]["history"]} == {"CANCELLED", "EXPIRED"}
    assert len({row["id"] for group in result["licenses"].values() for row in group}) == 3
    assert "license_key" not in str(result["licenses"])


def test_account_frontend_has_idempotent_license_rendering_and_real_dates():
    source = (Path(__file__).resolve().parents[1] / "miniapp" / "account-v2.js").read_text(encoding="utf-8")
    assert "new Map((rows || []).map(row => [String(row.id), row]))" in source
    assert "if (accountLoading) return" in source
    assert "row.display_expires_at" in source
    assert "timeZone: 'Asia/Tehran'" in source
    assert "لایسنس‌های فعال" in source and "تاریخچه لایسنس" in source


def test_api_repair_runs_before_config_import():
    source = (Path(__file__).resolve().parents[1] / "run_api.py").read_text(encoding="utf-8")
    assert source.index("repair_payment_owner_env()") < source.index("from app.combined_api import app")
