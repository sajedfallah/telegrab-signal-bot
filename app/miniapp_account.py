from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header

from . import db
from .miniapp_api import _auth_user, _entitlements
from .miniapp_experience import EXPIRING_DAYS, _parse_dt

router = APIRouter(prefix="/miniapp/api", tags=["NEXUS Mini App Account"])


def _service_status(*, active: bool, expires_at: Any, existed_before: bool, previous_expiry: Any) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    expiry = _parse_dt(expires_at) if active else _parse_dt(previous_expiry)
    if active:
        remaining = max(0, math.ceil((expiry - now).total_seconds() / 86400)) if expiry else None
        state = "EXPIRING" if remaining is not None and remaining <= EXPIRING_DAYS else "ACTIVE"
    elif existed_before and expiry and expiry <= now:
        remaining = 0
        state = "EXPIRED"
    else:
        remaining = None
        state = "INACTIVE"
    return {
        "state": state,
        "active": active,
        "expires_at": expiry.isoformat() if expiry else None,
        "remaining_days": remaining,
    }


def build_account_status(uid: int) -> dict[str, Any]:
    ent = _entitlements(uid)
    latest = db.latest_license(uid)
    old = dict(latest) if latest is not None else {}
    vip = _service_status(
        active=bool(ent.get("vip")),
        expires_at=ent.get("vip_expires_at"),
        existed_before=bool(old.get("vip_access")),
        previous_expiry=old.get("vip_expires_at") or old.get("expires_at"),
    )
    auto = _service_status(
        active=bool(ent.get("autotrade")),
        expires_at=ent.get("autotrade_expires_at"),
        existed_before=bool(old.get("autotrade_access")),
        previous_expiry=old.get("autotrade_expires_at") or old.get("expires_at"),
    )
    with db.conn() as con:
        mt5 = con.execute(
            "SELECT account_number,broker,server,status,ea_version,last_seen_at FROM autotrade_mt5_accounts WHERE telegram_id=? LIMIT 1",
            (uid,),
        ).fetchone()
        payment_count = int(con.execute("SELECT COUNT(*) FROM payments WHERE telegram_id=?", (uid,)).fetchone()[0])
    return {
        "vip": vip,
        "autotrade": {
            **auto,
            "mt5_bound": bool(mt5 and mt5["account_number"]),
            "ea_status": str(mt5["status"] or "") if mt5 else "",
            "last_seen_at": mt5["last_seen_at"] if mt5 else None,
        },
        "payments_count": payment_count,
    }


@router.get("/account/status")
def account_status(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    return build_account_status(uid)
