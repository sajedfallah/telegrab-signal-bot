from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess

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
    assert "new Map(valid.map(row => [String(row.id), row]))" in source
    assert "if (accountLoading) return" in source
    assert "cache: 'no-store'" in source
    assert "row.display_expires_at" in source
    assert "timeZone: 'Asia/Tehran'" in source
    assert "لایسنس‌های فعال" in source and "تاریخچه لایسنس" in source


def test_cancelled_license_payload_renders_only_history_cards():
    root = Path(__file__).resolve().parents[1]
    script = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync('miniapp/account-v2.js', 'utf8');
const view = {innerHTML:'<article class="account-v2-license current">stale</article>', dataset:{},
  querySelectorAll:()=>[], querySelector:()=>null};
const payload = {vip:{state:'INACTIVE'}, autotrade:{state:'INACTIVE'},
  licenses:{active:[],history:[
    {id:17,status:'CANCELLED',display_status:'CANCELLED'},
    {id:1,status:'CANCELLED',display_status:'CANCELLED'}]}};
const context = {view, state:{route:'account',bootstrap:{user:{id:5545027309}}},
  api:async (path, options) => {if(path !== '/account/status' || options.cache !== 'no-store') throw Error('stale account fetch'); return payload;},
  window:{NexusProduct:{skeleton:()=>'<div>loading</div>'}},
  document:{getElementById:()=>null}, MutationObserver:class{observe(){}},
  Intl, Date, Promise, console};
vm.runInNewContext(source, context);
context.window.NexusAccount.open().then(() => {
  const html = view.innerHTML;
  if((html.match(/account-v2-license current/g)||[]).length !== 0) throw Error('active card');
  if((html.match(/account-v2-license historical/g)||[]).length !== 2) throw Error('history count');
  if(!html.includes('موردی ثبت نشده است')) throw Error('active empty state');
}).catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(["node", "-e", script], cwd=root, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_purchase_flow_does_not_append_secondary_license_card_to_account():
    source = (Path(__file__).resolve().parents[1] / "miniapp" / "purchase-flow-v4.js").read_text(encoding="utf-8")
    enhancer = source.split("async function enhanceAccount()", 1)[1].split("function boot()", 1)[0]
    assert "licenseCard(ctx.license)" not in enhancer


def test_api_repair_runs_before_config_import():
    source = (Path(__file__).resolve().parents[1] / "run_api.py").read_text(encoding="utf-8")
    assert source.index("repair_payment_owner_env()") < source.index("from app.combined_api import app")
