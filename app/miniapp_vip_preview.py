from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header

from . import db
from .miniapp_api import _auth_user, _entitlements
from .miniapp_signals import CUSTOMER_INACTIVE_STATUSES

router = APIRouter(prefix="/miniapp/api", tags=["NEXUS Mini App VIP Preview"])


def _preview_status(value: Any) -> str:
    status = str(value or "").strip().upper()
    if status == "CLOSED":
        return "CLOSED"
    if "WAIT" in status or "PENDING" in status:
        return "WAITING"
    return "ACTIVE"


def build_vip_preview(*, has_vip: bool, limit: int = 5, now: datetime | None = None) -> dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = current.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    cycle = db.current_cycle_id()
    inactive = tuple(sorted(CUSTOMER_INACTIVE_STATUSES))
    marks = ",".join("?" for _ in inactive)
    with db.conn() as con:
        rows = [dict(row) for row in con.execute(
            f"""
            SELECT symbol,status,created_at,closed_at
            FROM signals
            WHERE UPPER(COALESCE(destination,'FREE'))='VIP'
              AND created_at>=?
              AND COALESCE(cycle_id,?)=?
              AND UPPER(COALESCE(status,'')) NOT IN ({marks})
            ORDER BY id DESC
            """,
            (start, cycle, cycle, *inactive),
        ).fetchall()]

    classified = [_preview_status(row.get("status")) for row in rows]
    summary = {
        "total": len(rows),
        "closed": sum(1 for value in classified if value == "CLOSED"),
        "active": sum(1 for value in classified if value == "ACTIVE"),
        "waiting": sum(1 for value in classified if value == "WAITING"),
    }
    return {
        "has_vip": bool(has_vip),
        "as_of": current.isoformat(),
        "summary": summary,
        "items": [] if has_vip else [
            {
                "symbol": str(row.get("symbol") or "—"),
                "status": _preview_status(row.get("status")),
                "locked": True,
            }
            for row in rows[:max(1, min(int(limit), 10))]
        ],
        "cta": None if has_vip else {
            "label": "Unlock NEXUS VIP — $19/month",
            "destination": "subscriptions",
        },
    }


@router.get("/vip-preview")
def vip_preview(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _auth_user(x_telegram_init_data)
    uid = int(user["id"])
    has_vip = bool(_entitlements(uid).get("vip"))
    return build_vip_preview(has_vip=has_vip)
