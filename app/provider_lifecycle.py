from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

import httpx

from .provider_credentials import load_secret
from .signal_domain import EVENT_TYPES, record_signal_event
from .telegram_tenant_domain import get_connection_private, resolve_destination


TERMINAL_EVENTS = {"TP_HIT", "SL_HIT", "MANUAL_CLOSE", "CLOSED"}
DELIVERY_STATUSES = {"CLAIMED", "SENT", "UNKNOWN"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_lifecycle_delivery_schema(con: sqlite3.Connection) -> None:
    statements = (
        """CREATE TABLE IF NOT EXISTS provider_lifecycle_deliveries(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            publication_id INTEGER NOT NULL,
            signal_id INTEGER NOT NULL,
            destination_key TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'CLAIMED'
                CHECK(status IN ('CLAIMED','SENT','UNKNOWN')),
            reply_to_message_id INTEGER,
            telegram_message_id INTEGER,
            event_id INTEGER,
            error_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(tenant_id,publication_id,idempotency_key),
            FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
            FOREIGN KEY(publication_id) REFERENCES signal_publications(id) ON DELETE CASCADE,
            FOREIGN KEY(signal_id) REFERENCES signals(id) ON DELETE CASCADE
        )""",
        "CREATE INDEX IF NOT EXISTS idx_provider_lifecycle_delivery_lookup ON provider_lifecycle_deliveries(tenant_id,signal_id,destination_key,status)",
    )
    for statement in statements:
        con.execute(statement)


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


def _payload_hash(event_type: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"event_type": str(event_type).upper(), "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


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


def _claim_delivery(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    publication: dict[str, Any],
    signal_id: int,
    destination_key: str,
    idempotency_key: str,
    event_type: str,
    payload: dict[str, Any],
    reply_to_message_id: int,
) -> tuple[dict[str, Any], bool]:
    init_lifecycle_delivery_schema(con)
    key = idempotency_key.strip()
    if not key:
        raise ValueError("idempotency_key is required")
    if len(key) > 160:
        raise ValueError("idempotency_key is too long")
    digest = _payload_hash(event_type, payload)
    now = _now()
    try:
        cur = con.execute(
            "INSERT INTO provider_lifecycle_deliveries(tenant_id,publication_id,signal_id,destination_key,idempotency_key,event_type,payload_hash,status,reply_to_message_id,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,'CLAIMED',?,?,?)",
            (
                tenant_id,
                int(publication["id"]),
                signal_id,
                destination_key.strip().upper(),
                key,
                event_type,
                digest,
                int(reply_to_message_id),
                now,
                now,
            ),
        )
        delivery_id = int(cur.lastrowid)
        # Durability boundary before external Telegram I/O. A process crash after
        # Telegram accepts the message cannot cause an automatic duplicate retry.
        con.commit()
        return {
            "id": delivery_id,
            "status": "CLAIMED",
            "payload_hash": digest,
            "event_type": event_type,
            "reply_to_message_id": int(reply_to_message_id),
        }, True
    except sqlite3.IntegrityError:
        row = con.execute(
            "SELECT id,status,event_type,payload_hash,reply_to_message_id,telegram_message_id,event_id,error_code "
            "FROM provider_lifecycle_deliveries WHERE tenant_id=? AND publication_id=? AND idempotency_key=?",
            (tenant_id, int(publication["id"]), key),
        ).fetchone()
        if row is None:
            raise
        existing = dict(row)
        if existing["event_type"] != event_type or existing["payload_hash"] != digest:
            raise RuntimeError("idempotency key reused with different lifecycle event")
        return existing, False


def _sent_receipt(
    delivery: dict[str, Any], publication: dict[str, Any], *, signal_id: int, destination_key: str
) -> dict[str, Any]:
    return {
        "ok": True,
        "idempotent_replay": True,
        "delivery_id": int(delivery["id"]),
        "event_id": int(delivery["event_id"]) if delivery.get("event_id") is not None else None,
        "event_type": str(delivery["event_type"]),
        "publication_id": int(publication["id"]),
        "signal_id": signal_id,
        "destination_key": destination_key.strip().upper(),
        "reply_to_message_id": int(delivery["reply_to_message_id"]),
        "message_id": int(delivery["telegram_message_id"]),
        "publication_status": str(publication.get("status") or "PUBLISHED"),
    }


def reply_signal_event(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    signal_id: int,
    destination_key: str,
    event_type: str,
    payload: dict[str, Any],
    idempotency_key: str,
    actor_user_id: int | None = None,
    timeout_seconds: float = 10.0,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Send one idempotent lifecycle update through a tenant-owned Telegram route.

    A durable delivery claim is committed before external I/O. Retrying the same
    idempotency key returns the stored receipt after success. CLAIMED/UNKNOWN
    outcomes are never re-sent automatically because Telegram may already have
    accepted the prior request. There is no global BOT_TOKEN/channel fallback.
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

    delivery, is_new = _claim_delivery(
        con,
        tenant_id=tenant_id,
        publication=publication,
        signal_id=signal_id,
        destination_key=destination_key,
        idempotency_key=idempotency_key,
        event_type=kind,
        payload=payload,
        reply_to_message_id=int(reply_to),
    )
    if not is_new:
        if delivery["status"] == "SENT":
            return _sent_receipt(delivery, publication, signal_id=signal_id, destination_key=destination_key)
        raise RuntimeError("lifecycle delivery outcome requires reconciliation")

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
        con.execute(
            "UPDATE provider_lifecycle_deliveries SET status='SENT',telegram_message_id=?,event_id=?,error_code=NULL,updated_at=? "
            "WHERE id=? AND tenant_id=?",
            (message_id, event_id, now, int(delivery["id"]), tenant_id),
        )
        con.commit()
        return {
            "ok": True,
            "idempotent_replay": False,
            "delivery_id": int(delivery["id"]),
            "event_id": event_id,
            "event_type": kind,
            "publication_id": int(publication["id"]),
            "signal_id": signal_id,
            "destination_key": str(publication["destination_key"]),
            "reply_to_message_id": int(reply_to),
            "message_id": message_id,
            "publication_status": status,
        }
    except Exception as exc:
        # Once the outbound request has started, delivery can be ambiguous. Persist
        # UNKNOWN and refuse automatic resend for the same idempotency key.
        try:
            con.execute(
                "UPDATE provider_lifecycle_deliveries SET status='UNKNOWN',error_code=?,updated_at=? WHERE id=? AND tenant_id=?",
                ("telegram_delivery_uncertain", _now(), int(delivery["id"]), tenant_id),
            )
            con.commit()
        except Exception:
            pass
        if isinstance(exc, (RuntimeError, ValueError)):
            raise
        if isinstance(exc, httpx.HTTPError):
            raise RuntimeError("Telegram lifecycle reply failed") from exc
        raise
    finally:
        if own_client:
            session.close()
