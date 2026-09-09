from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from . import db
from .miniapp_api import _auth_user, _entitlements
from .miniapp_home import _autotrade_health
from .miniapp_signals import serialize_signal

router = APIRouter(prefix="/miniapp/api", tags=["NEXUS Mini App Trades"])


def _require_autotrade(uid: int) -> dict[str, Any]:
    ent = _entitlements(uid)
    if not bool(ent.get("autotrade")):
        raise HTTPException(status_code=403, detail="active AutoTrade entitlement required")
    return ent


def _mt5_account(uid: int) -> dict[str, Any] | None:
    with db.conn() as con:
        row = con.execute(
            "SELECT account_number,broker,server,status,ea_version,bound_at,last_seen_at FROM autotrade_mt5_accounts WHERE telegram_id=? LIMIT 1",
            (uid,),
        ).fetchone()
    return dict(row) if row is not None else None


def _live_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "identifier": row.get("identifier"),
        "ticket": row.get("ticket"),
        "signal_code": row.get("signal_code"),
        "symbol": row.get("symbol"),
        "direction": row.get("direction"),
        "volume": row.get("volume"),
        "entry_price": row.get("entry_price"),
        "current_price": row.get("current_price"),
        "stop_loss": row.get("stop_loss"),
        "take_profit": row.get("take_profit"),
        "profit": row.get("profit"),
        "order_type": row.get("order_type"),
        "status": row.get("status"),
        "broker": row.get("broker"),
        "server": row.get("server"),
        "last_seen_at": row.get("last_seen_at"),
    }


def _history_item(row: Any) -> dict[str, Any]:
    item = dict(row)
    return {
        "id": int(item["id"]),
        "signal_id": int(item["signal_id"]) if item.get("signal_id") is not None else None,
        "ticket": str(item.get("ticket") or ""),
        "event_type": str(item.get("event_type") or ""),
        "symbol": item.get("symbol"),
        "direction": item.get("direction"),
        "volume": item.get("volume"),
        "entry_price": item.get("entry_price"),
        "stop_loss": item.get("stop_loss"),
        "take_profit": item.get("take_profit"),
        "exit_price": item.get("exit_price"),
        "profit": item.get("profit"),
        "gross_profit": item.get("gross_profit"),
        "commission": item.get("commission"),
        "swap": item.get("swap"),
        "slippage": item.get("slippage"),
        "status": item.get("status"),
        "created_at": item.get("created_at"),
    }


def _history(uid: int, *, limit: int, offset: int) -> list[dict[str, Any]]:
    with db.conn() as con:
        rows = con.execute(
            """
            SELECT id,signal_id,ticket,event_type,symbol,direction,volume,entry_price,stop_loss,take_profit,
                   exit_price,profit,gross_profit,commission,swap,slippage,status,created_at
            FROM autotrade_trade_executions
            WHERE telegram_id=?
            ORDER BY id DESC LIMIT ? OFFSET ?
            """,
            (uid, limit, offset),
        ).fetchall()
    return [_history_item(row) for row in rows]


def _snapshot(uid: int) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    mt5 = _mt5_account(uid)
    if not mt5 or not mt5.get("account_number"):
        return mt5, [], []
    account = str(mt5["account_number"])
    positions = [_live_item(row) for row in db.mt5_live_positions(account, nexus_only=True)]
    orders = [_live_item(row) for row in db.mt5_live_orders(account, nexus_only=True)]
    return mt5, positions, orders


@router.get("/autotrade/status")
def autotrade_status(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    ent = _require_autotrade(uid)
    mt5, positions, orders = _snapshot(uid)
    health = _autotrade_health({"entitled": True, "mt5": mt5, "open_positions": positions, "pending_orders": orders})
    license_row = db.active_license(uid)
    license_valid = bool(license_row is not None and int(license_row["autotrade_access"] or 0) == 1)
    return {
        "state": health,
        "checks": {
            "subscription": True,
            "license": license_valid,
            "mt5_account": bool(mt5 and mt5.get("account_number")),
            "ea_connected": bool(health and health.get("state") == "HEALTHY"),
        },
        "expires_at": ent.get("autotrade_expires_at"),
        "mt5": mt5,
    }


@router.get("/trades")
def trades(
    tab: str = Query(default="open"),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=5000),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    _require_autotrade(uid)
    key = str(tab or "open").lower()
    mt5, positions, orders = _snapshot(uid)
    if key == "open":
        items = positions[offset:offset + limit]
    elif key == "pending":
        items = orders[offset:offset + limit]
    elif key == "history":
        items = _history(uid, limit=limit, offset=offset)
    else:
        raise HTTPException(status_code=400, detail="unsupported trades tab")
    return {
        "tab": key,
        "limit": limit,
        "offset": offset,
        "mt5_bound": bool(mt5 and mt5.get("account_number")),
        "items": items,
    }


@router.get("/trades/{execution_id}")
def trade_detail(
    execution_id: int,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    ent = _require_autotrade(uid)
    with db.conn() as con:
        row = con.execute(
            """
            SELECT id,signal_id,ticket,event_type,symbol,direction,volume,entry_price,stop_loss,take_profit,
                   exit_price,profit,gross_profit,commission,swap,slippage,status,created_at
            FROM autotrade_trade_executions
            WHERE id=? AND telegram_id=? LIMIT 1
            """,
            (execution_id, uid),
        ).fetchone()
    if row is None:
        # Deliberately 404 rather than revealing whether another customer's ID exists.
        raise HTTPException(status_code=404, detail="trade not found")
    item = _history_item(row)
    signal_id = item.get("signal_id")
    signal = None
    if signal_id is not None:
        source = db.get_signal(int(signal_id))
        if source is not None:
            signal = serialize_signal(source, has_vip=bool(ent.get("vip")), include_timeline=False)
    return {"trade": item, "source_signal": signal}
