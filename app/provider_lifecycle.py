from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

import httpx

from .provider_credentials import load_secret
from .signal_domain import EVENT_TYPES, record_signal_event
from .telegram_tenant_domain import get_connection_private, resolve_destination


TERMINAL_EVENTS = {"TP_HIT", "SL_HIT", "MANUAL_CLOSE", "CLOSED"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _publication(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    signal_id: int,
    destination_key: str,
) -> dict[str, Any]:
    row = con.execute(
        "SELECT id,tenant_id,signal_id,destination_key,telegram_chat_id,root_message_id,last_message_id,status,published_at,updated_at "
        "FROM signal_publications WHERE tenant_id=? AND signal_id=? AND destination_key=?",
        (tenant_id, signal_id, destination_key.strip().upper()),
    ).fetchone()
    if row is None:
        raise LookupError("signal publication not found")
    return dict(row)


def _value(payload: dict[str, Any], *names: str) -> Any:
    for name in names:
        if payload.get(name) is not None:
            return payload[name]
    return None


def format_position_update(event_type: str, payload: dict[str, Any]) -> str:
    kind = str(event_type).upper()
    if kind not in EVENT_TYPES:
        raise ValueError("unsupported signal event type")

    titles = {
        "PARTIAL_CLOSE": "Partial Close Executed",
        "SL_CHANGED": "Stop Loss Updated",
        "TP_CHANGED": "Take Profit Updated",
        "BREAKEVEN": "Breakeven Activated",
        "TRAILING": "Trailing Stop Updated",
        "TP_HIT": "Take Profit Hit",
        "SL_HIT": "Stop Loss Hit",
        "MANUAL_CLOSE": "Position Closed Manually",
        "CLOSED": "Position Closed",
    }
    brand = str(payload.get("brand") or "NEXUS").strip()
    status = str(payload.get("position_status") or ("CLOSED" if kind in TERMINAL_EVENTS else "ACTIVE")).upper()
    tp = _value(payload, "tp", "take_profit", "current_tp", "new_tp")
    sl = _value(payload, "sl", "stop_loss", "current_sl", "new_sl")

    lines = [f"🔄 {brand} | POSITION UPDATE", "", titles[kind], ""]
    if kind == "PARTIAL_CLOSE":
        closed_volume = _value(payload, "closed_volume")
        closed_percent = _value(payload, "closed_percent")
        remaining_volume = _value(payload, "remaining_volume")
        remaining_percent = _value(payload, "remaining_percent")
        profit_usd = _value(payload, "profit_usd", "stage_profit_usd")
        if profit_usd is None:
            raise ValueError("PARTIAL_CLOSE requires profit_usd")
        if closed_volume is not None:
            lines.append(f"Closed Volume: {closed_volume}")
        if closed_percent is not None:
            lines.append(f"Closed: {closed_percent}%")
        if remaining_volume is not None:
            lines.append(f"Remaining Volume: {remaining_volume}")
        if remaining_percent is not None:
            lines.append(f"Remaining: {remaining_percent}%")
        lines.extend(["", f"Profit this stage: ${profit_usd}"])

    note = payload.get("note")
    if note:
        lines.extend(["", str(note).strip()])

    lines.extend(["", f"TP: {tp if tp is not None else '-'}", f"SL: {sl if sl is not None else '-'}", "", f"Position Status: {status}"])
    return "\n".join(lines)


def reply_signal_event(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    signal_id: int,
    destination_key: str,
    event_type: str,
    payload: dict[str, Any],
    actor_user_id: int | None = None,
    timeout_seconds: float = 10.0,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Send one lifecycle update through the publication's tenant-owned Telegram route.

    Replies chain from the publication's last_message_id (falling back to root_message_id).
    There is deliberately no global BOT_TOKEN/channel fallback.
    """
    kind = str(event_type).upper()
    if kind not in EVENT_TYPES:
        raise ValueError("unsupported signal event type")

    publication = _publication(
        con,
        tenant_id=tenant_id,
        signal_id=signal_id,
        destination_key=destination_key,
    )
    if publication.get("status") == "CLOSED":
        raise RuntimeError("signal publication is closed")

    destination = resolve_destination(con, tenant_id=tenant_id, destination_key=destination_key)
    if destination is None:
        raise LookupError("Telegram destination not found or inactive")
    if str(destination["chat_id"]) != str(publication.get("telegram_chat_id")):
        raise RuntimeError("publication route no longer matches destination")

    connection = get_connection_private(
        con, tenant_id=tenant_id, connection_id=int(destination["connection_id"])
    )
    if connection.get("status") != "ACTIVE" or not connection.get("secret_ref"):
        raise RuntimeError("Telegram connection is not publish-ready")
    token = load_secret(con, tenant_id=tenant_id, secret_ref=str(connection["secret_ref"]))

    text = format_position_update(kind, payload)
    reply_to = publication.get("last_message_id") or publication.get("root_message_id")
    if reply_to is None:
        raise RuntimeError("signal publication has no Telegram root message")

    request: dict[str, Any] = {
        "chat_id": str(publication["telegram_chat_id"]),
        "text": text,
        "reply_parameters": {"message_id": int(reply_to), "allow_sending_without_reply": False},
    }
    if destination.get("thread_id") is not None:
        request["message_thread_id"] = int(destination["thread_id"])

    own_client = client is None
    session = client or httpx.Client(timeout=timeout_seconds)
    try:
        response = session.post(f"https://api.telegram.org/bot{token}/sendMessage", json=request)
        if response.status_code != 200:
            raise RuntimeError("Telegram lifecycle reply failed")
        body = response.json()
        result = body.get("result") if isinstance(body, dict) else None
        if not body.get("ok") or not isinstance(result, dict) or result.get("message_id") is None:
            raise RuntimeError("Telegram lifecycle reply failed")
        message_id = int(result["message_id"])
        event_id = record_signal_event(
            con,
            tenant_id=tenant_id,
            signal_id=signal_id,
            event_type=kind,
            payload=payload,
            actor_user_id=actor_user_id,
        )
        now = _now()
        status = "CLOSED" if kind in TERMINAL_EVENTS else publication.get("status") or "PUBLISHED"
        con.execute(
            "UPDATE signal_publications SET last_message_id=?,status=?,updated_at=? "
            "WHERE id=? AND tenant_id=? AND signal_id=?",
            (message_id, status, now, int(publication["id"]), tenant_id, signal_id),
        )
        return {
            "ok": True,
            "event_id": event_id,
            "event_type": kind,
            "publication_id": int(publication["id"]),
            "signal_id": signal_id,
            "destination_key": str(publication["destination_key"]),
            "reply_to_message_id": int(reply_to),
            "message_id": message_id,
            "publication_status": status,
        }
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError("Telegram lifecycle reply failed") from exc
    finally:
        if own_client:
            session.close()
