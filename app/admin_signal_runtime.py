from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db
from .admin_api import current_admin, require_admin
from .config import settings
from .web_chart_capture_runtime import (
    _publish_web_signal,
    chart_agent_status,
    create_web_signal,
    publication_status,
    retry_chart,
)

router = APIRouter(prefix="/api/v1/admin-web", tags=["admin-web-signals"])


class WebSignalWrite(BaseModel):
    request_id: str = Field(min_length=8, max_length=160)
    market_type: str = Field(pattern="^(FOREX|CRYPTO|GOLD|INDEX|OTHER)$")
    symbol: str = Field(min_length=2, max_length=64)
    direction: str = Field(pattern="^(BUY|SELL|LONG|SHORT)$")
    timeframe: str = Field(default="M5", pattern="^(M1|M3|M5|M15|M30|H1|H4|D1|W1)$")
    order_type: str = Field(default="MARKET", pattern="^(MARKET|LIMIT|BUY_LIMIT|SELL_LIMIT|BUY_STOP|SELL_STOP|BUY_STOP_LIMIT|SELL_STOP_LIMIT)$")
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    targets: list[float] = Field(min_length=1, max_length=10)
    risk_percent: float = Field(default=1.0, ge=0, le=10)
    rr_ratio: float | None = Field(default=None, gt=0)
    destination: str = Field(default="BOTH", pattern="^(FREE|VIP|BOTH)$")
    volume_mode: str = Field(default="RISK", pattern="^(RISK|FIXED)$")
    lot_size: float | None = Field(default=None, gt=0)
    leverage: float | None = Field(default=None, gt=0)
    trailing_code: str | None = Field(default=None, max_length=64)
    trailing_name: str | None = Field(default=None, max_length=128)
    max_entry_deviation_pct: float | None = Field(default=None, gt=0)
    max_entry_deviation_abs: float | None = Field(default=None, gt=0)
    stop_limit_price: float | None = Field(default=None, gt=0)
    issuer_account: str = Field(min_length=3, max_length=32)


def _audit_signal_issue_once(*, admin_id: int, signal_id: int, request_id: str, code: str) -> None:
    details = f"request_id={request_id};code={code}"
    now = db.now_iso()
    with db.conn() as con:
        con.execute(
            """
            INSERT INTO audit_logs(admin_id,action,target_id,details,created_at)
            SELECT ?,?,?,?,?
            WHERE NOT EXISTS (
                SELECT 1 FROM audit_logs
                WHERE admin_id=? AND action='web_signal_issued' AND target_id=? AND details=?
            )
            """,
            (
                int(admin_id),
                "web_signal_issued",
                int(signal_id),
                details,
                now,
                int(admin_id),
                int(signal_id),
                details,
            ),
        )


@router.get("/chart-agents")
def chart_agents(admin=Depends(current_admin)):
    status = chart_agent_status()
    allowed = set(settings.nexus_admin_mt5_accounts)
    items = [item for item in status.get("items", []) if str(item.get("account_number")) in allowed]
    known = {str(item.get("account_number")) for item in items}
    for account in settings.nexus_admin_mt5_accounts:
        if account not in known:
            items.append({"account_number": account, "online": False, "last_seen_at": None})
    return {"items": items}


@router.post("/signals/issue", status_code=201)
def issue_web_signal(req: WebSignalWrite, admin=Depends(require_admin)):
    try:
        row = create_web_signal(
            payload=req.model_dump(exclude={"issuer_account", "request_id"}),
            admin_id=int(admin["id"]),
            issuer_account=req.issuer_account,
            request_id=req.request_id,
        )
        state = publication_status(int(row["id"]))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _audit_signal_issue_once(
        admin_id=int(admin["id"]),
        signal_id=int(row["id"]),
        request_id=req.request_id,
        code=str(row["code"]),
    )
    return {
        "id": int(row["id"]),
        "code": str(row["code"]),
        "status": str(row["status"]),
        "publication_stage": str(state["publication"]["stage"]),
        "job": state["job"],
    }


@router.get("/signals/{signal_id}/publication")
def get_publication(signal_id: int, admin=Depends(current_admin)):
    try:
        return publication_status(signal_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/signals/{signal_id}/chart/retry")
def retry_signal_chart(signal_id: int, admin=Depends(require_admin)):
    row = db.get_signal(signal_id)
    if not row or str(row["issuer_type"] or "").upper() != "WEB_ADMIN":
        raise HTTPException(status_code=404, detail="Web signal not found")
    try:
        state = retry_chart(signal_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.add_audit(int(admin["id"]), "web_signal_chart_retry", signal_id, str(row["code"]))
    return state


@router.post("/signals/{signal_id}/publication/retry", status_code=202)
def retry_publication(signal_id: int, background_tasks: BackgroundTasks, admin=Depends(require_admin)):
    row = db.get_signal(signal_id)
    if not row or str(row["issuer_type"] or "").upper() != "WEB_ADMIN":
        raise HTTPException(status_code=404, detail="Web signal not found")
    try:
        state = publication_status(signal_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    stage = str(state["publication"]["stage"])
    if stage not in {"CHART_RECEIVED", "PUBLISH_FAILED"}:
        raise HTTPException(status_code=409, detail=f"Publication cannot be retried from stage {stage}")
    background_tasks.add_task(_publish_web_signal, signal_id)
    db.add_audit(int(admin["id"]), "web_signal_publication_retry", signal_id, str(row["code"]))
    return {"ok": True, "status": "QUEUED"}


@router.post("/signals/{signal_id}/cancel")
def cancel_web_signal(signal_id: int, admin=Depends(require_admin)):
    row = db.get_signal(signal_id)
    if not row or str(row["issuer_type"] or "").upper() != "WEB_ADMIN":
        raise HTTPException(status_code=404, detail="Web signal not found")
    try:
        state = publication_status(signal_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if str(state["publication"]["stage"]) == "PUBLISHED" or str(row["status"]).upper() == "ACTIVE":
        raise HTTPException(status_code=409, detail="Published/active signals must be managed through trade commands, not canceled")
    now = db.now_iso()
    with db.conn() as con:
        con.execute("UPDATE signals SET status='CANCELED' WHERE id=?", (signal_id,))
        con.execute(
            "UPDATE web_signal_publications SET stage='CANCELED',updated_at=? WHERE signal_id=?",
            (now, signal_id),
        )
        con.execute(
            "UPDATE signal_chart_capture_jobs SET status='FAILED',error_text='Canceled by admin',updated_at=? WHERE signal_id=? AND status IN ('PENDING','CLAIMED','CAPTURING')",
            (now, signal_id),
        )
    db.add_audit(int(admin["id"]), "web_signal_canceled", signal_id, str(row["code"]))
    return {"ok": True, "status": "CANCELED"}


def new_request_id() -> str:
    return "WEB-" + secrets.token_urlsafe(18)
