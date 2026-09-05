from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from pydantic import BaseModel, Field

from . import db
from .autotrade.service import AutoTradeError, authorize_admin_mt5
from .config import settings

router = APIRouter(prefix="/api/v1/autotrade/admin/chart-capture", tags=["web-mt5-chart-capture"])
_INSTALLED = False
_ACTIVE_SIGNALS_PATCHED = False
MAX_IMAGE_BYTES = 5_000_000
MAX_ATTEMPTS = 3
CLAIM_STALE_SECONDS = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_schema() -> None:
    with db.conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS web_signal_publications (
                signal_id INTEGER PRIMARY KEY,
                request_id TEXT NOT NULL UNIQUE,
                stage TEXT NOT NULL,
                requested_by INTEGER NOT NULL,
                issuer_account TEXT NOT NULL,
                screenshot_path TEXT,
                error_text TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                published_at TEXT,
                FOREIGN KEY(signal_id) REFERENCES signals(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS signal_chart_capture_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                claimed_by_account TEXT,
                claimed_at TEXT,
                next_attempt_at TEXT,
                error_text TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY(signal_id) REFERENCES signals(id) ON DELETE CASCADE
            );

            CREATE UNIQUE INDEX IF NOT EXISTS ux_chart_capture_active_signal
                ON signal_chart_capture_jobs(signal_id)
                WHERE status IN ('PENDING','CLAIMED','CAPTURING');
            CREATE INDEX IF NOT EXISTS idx_chart_capture_status_time
                ON signal_chart_capture_jobs(status,next_attempt_at,id);

            CREATE TABLE IF NOT EXISTS web_chart_agents (
                account_number TEXT PRIMARY KEY,
                ea_version TEXT,
                broker TEXT,
                server TEXT,
                last_seen_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )


def _auth(account: str | None, token: str | None) -> dict[str, Any]:
    account = str(account or "").strip()
    if not account:
        raise HTTPException(status_code=401, detail="missing MT5 admin account")
    try:
        return authorize_admin_mt5(account, token)
    except AutoTradeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _touch_agent(account: str, *, version: str = "", broker: str = "", server: str = "") -> None:
    ensure_schema()
    now = _now()
    with db.conn() as con:
        con.execute(
            """INSERT INTO web_chart_agents(account_number,ea_version,broker,server,last_seen_at,updated_at)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(account_number) DO UPDATE SET
                 ea_version=excluded.ea_version,broker=excluded.broker,server=excluded.server,
                 last_seen_at=excluded.last_seen_at,updated_at=excluded.updated_at""",
            (account, version or None, broker or None, server or None, now, now),
        )


def chart_agent_status(account: str | None = None) -> dict[str, Any]:
    ensure_schema()
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=120)
    with db.conn() as con:
        if account:
            row = con.execute("SELECT * FROM web_chart_agents WHERE account_number=?", (str(account),)).fetchone()
            if not row:
                return {"account_number": str(account), "online": False, "last_seen_at": None}
            item = dict(row)
            try:
                online = datetime.fromisoformat(str(item["last_seen_at"])) >= cutoff
            except Exception:
                online = False
            return {**item, "online": bool(online)}
        rows = con.execute("SELECT * FROM web_chart_agents ORDER BY last_seen_at DESC").fetchall()
    return {"items": [
        {**dict(r), "online": (datetime.fromisoformat(str(r["last_seen_at"])) >= cutoff)}
        for r in rows
    ]}


def _existing_by_request(request_id: str):
    ensure_schema()
    with db.conn() as con:
        return con.execute(
            """SELECT s.*,p.stage AS publication_stage,p.error_text AS publication_error
               FROM web_signal_publications p JOIN signals s ON s.id=p.signal_id
               WHERE p.request_id=?""",
            (request_id,),
        ).fetchone()


def create_web_signal(*, payload: dict[str, Any], admin_id: int, issuer_account: str, request_id: str | None = None):
    """Create a web-authored signal without exposing it to customer EAs yet."""
    ensure_schema()
    account = str(issuer_account or "").strip()
    if not account or account not in settings.nexus_admin_mt5_accounts:
        raise ValueError("a valid allow-listed MT5 chart account is required")
    rid = str(request_id or "").strip() or ("WEB-" + secrets.token_urlsafe(18))
    existing = _existing_by_request(rid)
    if existing:
        return existing

    row = db.create_signal(
        market_type=payload["market_type"],
        symbol=payload["symbol"],
        direction=payload["direction"],
        entry_price=payload["entry_price"],
        stop_loss=payload["stop_loss"],
        targets=payload["targets"],
        risk_percent=payload["risk_percent"],
        rr_ratio=payload.get("rr_ratio"),
        destination=payload["destination"],
        chart_file_id=None,
        created_by=int(admin_id),
        lot_size=payload.get("lot_size"),
        leverage=payload.get("leverage"),
        trailing_code=payload.get("trailing_code"),
        trailing_name=payload.get("trailing_name"),
        max_entry_deviation_pct=payload.get("max_entry_deviation_pct"),
        max_entry_deviation_abs=payload.get("max_entry_deviation_abs"),
        order_type=payload.get("order_type", "MARKET"),
        volume_mode=payload.get("volume_mode", "RISK"),
        publish_token=rid,
        timeframe=payload.get("timeframe", "M5"),
        stop_limit_price=payload.get("stop_limit_price"),
    )
    now = _now()
    suuid = str(__import__("uuid").uuid4())
    with db.conn() as con:
        con.execute(
            """UPDATE signals SET signal_uuid=?,revision=1,issuer_type='WEB_ADMIN',issuer_account=?,issued_at=?,status='DRAFT'
               WHERE id=?""",
            (suuid, account, now, int(row["id"])),
        )
        con.execute(
            """INSERT INTO web_signal_publications(signal_id,request_id,stage,requested_by,issuer_account,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?)""",
            (int(row["id"]), rid, "WAITING_FOR_CHART", int(admin_id), account, now, now),
        )
        con.execute(
            """INSERT INTO signal_chart_capture_jobs(signal_id,status,attempt_count,next_attempt_at,created_at,updated_at)
               VALUES(?,'PENDING',0,?,?,?)""",
            (int(row["id"]), now, now, now),
        )
        final = con.execute(
            """SELECT s.*,p.stage AS publication_stage,p.error_text AS publication_error
               FROM signals s JOIN web_signal_publications p ON p.signal_id=s.id WHERE s.id=?""",
            (int(row["id"]),),
        ).fetchone()
    db.add_signal_event(
        int(final["id"]), "ISSUE", actor_type="WEB_ADMIN", actor_id=int(admin_id),
        account_number=account, revision=1, request_id=rid, correlation_id=str(final["code"]),
        payload={"symbol": str(final["symbol"]), "direction": str(final["direction"]), "stage": "WAITING_FOR_CHART"},
    )
    return final


def publication_status(signal_id: int) -> dict[str, Any]:
    ensure_schema()
    with db.conn() as con:
        p = con.execute("SELECT * FROM web_signal_publications WHERE signal_id=?", (int(signal_id),)).fetchone()
        j = con.execute("SELECT * FROM signal_chart_capture_jobs WHERE signal_id=? ORDER BY id DESC LIMIT 1", (int(signal_id),)).fetchone()
    if not p:
        raise ValueError("web publication not found")
    return {"publication": dict(p), "job": dict(j) if j else None}


def retry_chart(signal_id: int) -> dict[str, Any]:
    ensure_schema()
    now = _now()
    with db.conn() as con:
        p = con.execute("SELECT * FROM web_signal_publications WHERE signal_id=?", (int(signal_id),)).fetchone()
        if not p:
            raise ValueError("web publication not found")
        if str(p["stage"]) == "PUBLISHED":
            return publication_status(signal_id)
        con.execute(
            "UPDATE signal_chart_capture_jobs SET status='FAILED',updated_at=? WHERE signal_id=? AND status IN ('PENDING','CLAIMED','CAPTURING')",
            (now, int(signal_id)),
        )
        con.execute(
            "INSERT INTO signal_chart_capture_jobs(signal_id,status,attempt_count,next_attempt_at,created_at,updated_at) VALUES(?,'PENDING',0,?,?,?)",
            (int(signal_id), now, now, now),
        )
        con.execute(
            "UPDATE web_signal_publications SET stage='WAITING_FOR_CHART',error_text=NULL,updated_at=? WHERE signal_id=?",
            (now, int(signal_id)),
        )
    return publication_status(signal_id)


def _claim_job(account: str):
    ensure_schema()
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    stale = (now_dt - timedelta(seconds=CLAIM_STALE_SECONDS)).isoformat()
    with db.conn() as con:
        con.execute("BEGIN IMMEDIATE")
        con.execute(
            """UPDATE signal_chart_capture_jobs SET status='PENDING',claimed_by_account=NULL,claimed_at=NULL,updated_at=?
               WHERE status IN ('CLAIMED','CAPTURING') AND claimed_at<? AND attempt_count<?""",
            (now, stale, MAX_ATTEMPTS),
        )
        row = con.execute(
            """SELECT j.*,s.code,s.symbol,s.timeframe,s.direction,s.entry_price,s.stop_loss,s.issuer_account
               FROM signal_chart_capture_jobs j JOIN signals s ON s.id=j.signal_id
               WHERE j.status='PENDING' AND j.attempt_count<? AND (j.next_attempt_at IS NULL OR j.next_attempt_at<=?)
                 AND s.issuer_type='WEB_ADMIN' AND s.issuer_account=?
               ORDER BY j.id LIMIT 1""",
            (MAX_ATTEMPTS, now, account),
        ).fetchone()
        if not row:
            return None
        cur = con.execute(
            """UPDATE signal_chart_capture_jobs SET status='CLAIMED',claimed_by_account=?,claimed_at=?,attempt_count=attempt_count+1,updated_at=?
               WHERE id=? AND status='PENDING'""",
            (account, now, now, int(row["id"])),
        )
        if cur.rowcount != 1:
            return None
        job = con.execute(
            """SELECT j.*,s.code,s.symbol,s.timeframe,s.direction,s.entry_price,s.stop_loss,s.issuer_account
               FROM signal_chart_capture_jobs j JOIN signals s ON s.id=j.signal_id WHERE j.id=?""",
            (int(row["id"]),),
        ).fetchone()
    targets = [float(t["price"]) for t in db.get_signal_targets(int(job["signal_id"]))]
    return {**dict(job), "targets": targets}


class AgentHeartbeat(BaseModel):
    ea_version: str = Field(default="", max_length=64)
    broker: str = Field(default="", max_length=128)
    server: str = Field(default="", max_length=128)


@router.post("/heartbeat")
def agent_heartbeat(
    req: AgentHeartbeat,
    x_mt5_account: str | None = Header(None),
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
):
    auth = _auth(x_mt5_account, x_admin_token)
    account = str(auth["account_number"])
    _touch_agent(account, version=req.ea_version, broker=req.broker, server=req.server)
    return {"ok": True, "account_number": account}


@router.get("/next")
def next_job(
    x_mt5_account: str | None = Header(None),
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
    x_ea_version: str | None = Header(None),
):
    auth = _auth(x_mt5_account, x_admin_token)
    account = str(auth["account_number"])
    _touch_agent(account, version=str(x_ea_version or ""))
    job = _claim_job(account)
    if not job:
        return {"ok": True, "job": None}
    return {
        "ok": True,
        "job": {
            "job_id": int(job["id"]),
            "signal_db_id": int(job["signal_id"]),
            "signal_code": str(job["code"]),
            "symbol": str(job["symbol"]),
            "timeframe": str(job["timeframe"] or "M5"),
            "direction": str(job["direction"]),
            "entry": float(job["entry_price"]),
            "sl": float(job["stop_loss"]),
            "targets": job["targets"],
        },
    }


class CaptureResult(BaseModel):
    signal_db_id: int = Field(gt=0)
    signal_code: str = Field(min_length=3, max_length=64)
    broker_symbol: str = Field(min_length=1, max_length=64)
    timeframe: str = Field(min_length=2, max_length=16)
    image_base64: str = Field(min_length=16, max_length=7_000_000)
    image_sha256: str = Field(min_length=64, max_length=64)


async def _publish_web_signal(signal_id: int) -> dict[str, Any]:
    row = db.get_signal(int(signal_id))
    if not row:
        return {"complete": False, "errors": ["signal not found"]}
    with db.conn() as con:
        pub = con.execute("SELECT * FROM web_signal_publications WHERE signal_id=?", (int(signal_id),)).fetchone()
    if not pub or not pub["screenshot_path"]:
        return {"complete": False, "errors": ["screenshot missing"]}

    try:
        raw = Path(str(pub["screenshot_path"])).read_bytes()
        from .signals.card_generator import build_chart_frame
        chart_frame = await asyncio.to_thread(build_chart_frame, raw)
    except Exception as exc:
        with db.conn() as con:
            con.execute("UPDATE web_signal_publications SET stage='PUBLISH_FAILED',error_text=?,updated_at=? WHERE signal_id=?", (f"render: {exc}", _now(), int(signal_id)))
        return {"complete": False, "errors": [f"render: {exc}"]}

    target_rows = db.get_signal_targets(int(signal_id))
    target_map = {int(t["target_no"]): float(t["price"]) for t in target_rows}
    tp_lines = "\n".join(f"🎯 TP{n}: <code>{target_map[n]:g}</code>" for n in sorted(target_map)) or "🎯 TP: —"
    caption = (
        "<b>━━━━━━━━ NEXUS SIGNAL ━━━━━━━━</b>\n"
        f"<b>{row['code']}</b>  🟦 {str(row['order_type'] or 'MARKET').upper()}\n\n"
        f"📌 Symbol: <b>{str(row['symbol']).upper()}</b>\n"
        f"↕️ Direction: <b>{str(row['direction']).upper()}</b>\n"
        f"⏱ Timeframe: <b>{str(row['timeframe'] or 'M5').upper()}</b>\n"
        f"📍 Entry: <code>{float(row['entry_price']):g}</code>\n"
        f"🛑 Stop Loss: <code>{float(row['stop_loss']):g}</code>\n"
        f"{tp_lines}\n"
        f"📊 Risk: <b>{float(row['risk_percent']):g}%</b>\n"
        "📌 Status: <b>ACTIVE</b>\n"
        f"🔧 Trailing: <b>{row['trailing_code'] or '—'}</b>"
    )

    destination = str(row["destination"] or "BOTH").upper()
    errors: list[str] = []
    free_id = vip_id = None
    async with Bot(settings.bot_token) as bot:
        routes: list[tuple[str, Any]] = []
        if destination in {"FREE", "BOTH"}:
            routes.append(("FREE", settings.free_channel_target))
        if destination in {"VIP", "BOTH"}:
            routes.append(("VIP", settings.vip_channel_id))
        for channel, target in routes:
            if not db.claim_signal_channel(int(signal_id), channel):
                continue
            try:
                msg = await bot.send_photo(
                    target,
                    BufferedInputFile(chart_frame, filename=f"{row['code']}_chart.png"),
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
                if channel == "FREE":
                    free_id = int(msg.message_id)
                else:
                    vip_id = int(msg.message_id)
            except Exception as exc:
                db.release_signal_channel_claim(int(signal_id), channel)
                errors.append(f"{channel}: {exc}")

    if free_id is not None or vip_id is not None:
        db.set_signal_publish_messages(int(signal_id), free_id, vip_id)

    # Existing message IDs count as already-published for idempotent retries.
    fresh = db.get_signal(int(signal_id))
    have_free = bool(fresh["free_message_id"])
    have_vip = bool(fresh["vip_message_id"])
    complete = (
        (destination == "FREE" and have_free)
        or (destination == "VIP" and have_vip)
        or (destination == "BOTH" and have_free and have_vip)
    )
    now = _now()
    with db.conn() as con:
        con.execute(
            "UPDATE web_signal_publications SET stage=?,error_text=?,updated_at=?,published_at=? WHERE signal_id=?",
            ("PUBLISHED" if complete else "PUBLISH_FAILED", "; ".join(errors) or None, now, now if complete else None, int(signal_id)),
        )
        if complete:
            con.execute("UPDATE signals SET status='ACTIVE' WHERE id=? AND issuer_type='WEB_ADMIN'", (int(signal_id),))
    db.add_signal_event(
        int(signal_id), "PUBLISH", actor_type="WEB_ADMIN", actor_id=int(pub["requested_by"]),
        account_number=str(pub["issuer_account"]), correlation_id=str(row["code"]),
        payload={"free_message_id": fresh["free_message_id"], "vip_message_id": fresh["vip_message_id"], "errors": errors, "complete": complete},
    )
    return {"complete": bool(complete), "errors": errors}


@router.post("/{job_id}/result")
def capture_result(
    job_id: int,
    req: CaptureResult,
    background_tasks: BackgroundTasks,
    x_mt5_account: str | None = Header(None),
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
):
    auth = _auth(x_mt5_account, x_admin_token)
    account = str(auth["account_number"])
    ensure_schema()
    with db.conn() as con:
        job = con.execute(
            """SELECT j.*,s.code,s.issuer_account FROM signal_chart_capture_jobs j
               JOIN signals s ON s.id=j.signal_id WHERE j.id=?""",
            (int(job_id),),
        ).fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="chart capture job not found")
    if str(job["claimed_by_account"] or "") != account or str(job["issuer_account"] or "") != account:
        raise HTTPException(status_code=403, detail="chart capture job belongs to another account")
    if int(job["signal_id"]) != int(req.signal_db_id) or str(job["code"]) != str(req.signal_code):
        raise HTTPException(status_code=409, detail="signal identity mismatch")
    if str(job["status"]) == "COMPLETED":
        return {"ok": True, "idempotent": True}
    if str(job["status"]) not in {"CLAIMED", "CAPTURING"}:
        raise HTTPException(status_code=409, detail="chart capture job is not claimed")

    try:
        raw = base64.b64decode(req.image_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=422, detail="invalid image encoding") from exc
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="chart image is empty or too large")
    if not (raw.startswith(b"\x89PNG\r\n\x1a\n") or raw.startswith(b"\xff\xd8\xff")):
        raise HTTPException(status_code=422, detail="chart image must be PNG or JPEG")
    if hashlib.sha256(raw).hexdigest().lower() != req.image_sha256.lower():
        raise HTTPException(status_code=422, detail="chart image sha256 mismatch")
    try:
        from PIL import Image, UnidentifiedImageError
        with Image.open(BytesIO(raw)) as image:
            image.verify()
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > 20_000_000:
                raise ValueError("unsafe image dimensions")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="invalid chart image") from exc

    folder = Path(__file__).resolve().parent / "assets" / "autotrade" / "pending_signal_charts"
    folder.mkdir(parents=True, exist_ok=True)
    ext = "png" if raw.startswith(b"\x89PNG") else "jpg"
    path = folder / f"web_{int(job['signal_id'])}_{int(job_id)}.{ext}"
    path.write_bytes(raw)
    now = _now()
    with db.conn() as con:
        con.execute(
            "UPDATE signal_chart_capture_jobs SET status='COMPLETED',completed_at=?,updated_at=?,error_text=NULL WHERE id=?",
            (now, now, int(job_id)),
        )
        con.execute(
            "UPDATE web_signal_publications SET stage='CHART_RECEIVED',screenshot_path=?,error_text=NULL,updated_at=? WHERE signal_id=?",
            (str(path), now, int(job["signal_id"])),
        )
    background_tasks.add_task(_publish_web_signal, int(job["signal_id"]))
    return {"ok": True, "publication": "QUEUED"}


class CaptureFailure(BaseModel):
    error_code: str = Field(default="CAPTURE_FAILED", max_length=64)
    error_text: str = Field(min_length=1, max_length=1000)


@router.post("/{job_id}/fail")
def capture_fail(
    job_id: int,
    req: CaptureFailure,
    x_mt5_account: str | None = Header(None),
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
):
    auth = _auth(x_mt5_account, x_admin_token)
    account = str(auth["account_number"])
    ensure_schema()
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    with db.conn() as con:
        job = con.execute("SELECT * FROM signal_chart_capture_jobs WHERE id=?", (int(job_id),)).fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="chart capture job not found")
        if str(job["claimed_by_account"] or "") != account:
            raise HTTPException(status_code=403, detail="chart capture job belongs to another account")
        attempts = int(job["attempt_count"] or 0)
        if attempts < MAX_ATTEMPTS:
            delay = 3 if attempts <= 1 else 7
            next_at = (now_dt + timedelta(seconds=delay)).isoformat()
            status = "PENDING"
        else:
            next_at = None
            status = "FAILED"
        con.execute(
            """UPDATE signal_chart_capture_jobs SET status=?,next_attempt_at=?,error_text=?,claimed_by_account=NULL,claimed_at=NULL,updated_at=? WHERE id=?""",
            (status, next_at, f"{req.error_code}: {req.error_text}", now, int(job_id)),
        )
        con.execute(
            "UPDATE web_signal_publications SET stage=?,error_text=?,updated_at=? WHERE signal_id=?",
            ("WAITING_FOR_CHART" if status == "PENDING" else "CAPTURE_FAILED", req.error_text, now, int(job["signal_id"])),
        )
    return {"ok": True, "status": status, "next_attempt_at": next_at}


def _patch_active_signals() -> None:
    global _ACTIVE_SIGNALS_PATCHED
    if _ACTIVE_SIGNALS_PATCHED:
        return

    def _active(after_id: int = 0, limit: int = 50):
        with db.conn() as con:
            return list(con.execute(
                """SELECT * FROM signals
                   WHERE id>? AND status='ACTIVE'
                     AND issuer_type IN ('MT5_ADMIN','WEB_ADMIN')
                   ORDER BY id ASC LIMIT ?""",
                (int(after_id), max(1, min(int(limit), 100))),
            ).fetchall())

    db.autotrade_active_signals = _active
    _ACTIVE_SIGNALS_PATCHED = True


def install_web_chart_capture_runtime() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    ensure_schema()
    _patch_active_signals()
    from .autotrade.api import app
    if not any(getattr(route, "path", "").startswith("/api/v1/autotrade/admin/chart-capture") for route in app.routes):
        app.include_router(router)
    db.set_setting("web_mt5_chart_capture_enabled", "1")
    _INSTALLED = True
