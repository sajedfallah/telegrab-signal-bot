from __future__ import annotations

import sqlite3
from typing import Any

import httpx

from .provider_credentials import load_secret
from .telegram_tenant_domain import get_connection_private, resolve_destination


def _signal_owned(con: sqlite3.Connection, *, tenant_id: int, signal_id: int) -> bool:
    row = con.execute(
        "SELECT 1 FROM signals WHERE id=? AND tenant_id=?", (signal_id, tenant_id)
    ).fetchone()
    return row is not None


def _existing_publication(
    con: sqlite3.Connection, *, tenant_id: int, signal_id: int, destination_key: str
) -> dict[str, Any] | None:
    row = con.execute(
        "SELECT id,destination_key,telegram_chat_id,root_message_id,last_message_id,status,published_at,updated_at "
        "FROM signal_publications WHERE tenant_id=? AND signal_id=? AND destination_key=?",
        (tenant_id, signal_id, destination_key.strip().upper()),
    ).fetchone()
    return dict(row) if row is not None else None


def record_publication_receipt(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    signal_id: int,
    destination_key: str,
    chat_id: str,
    message_id: int,
    published_at: str,
) -> int:
    if not _signal_owned(con, tenant_id=tenant_id, signal_id=signal_id):
        raise LookupError("signal not found")
    cur = con.execute(
        "INSERT INTO signal_publications(tenant_id,signal_id,destination_key,telegram_chat_id,root_message_id,last_message_id,status,published_at,updated_at) "
        "VALUES(?,?,?,?,?,?,'PUBLISHED',?,?)",
        (
            tenant_id,
            signal_id,
            destination_key.strip().upper(),
            str(chat_id),
            int(message_id),
            int(message_id),
            published_at,
            published_at,
        ),
    )
    return int(cur.lastrowid)


def publish_signal_text(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    signal_id: int,
    destination_key: str,
    text: str,
    timeout_seconds: float = 10.0,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Publish through the tenant's own tested bot and destination only.

    There is deliberately no BOT_TOKEN, global channel, or NEXUS routing fallback.
    """
    from .signal_domain import init_signal_domain_schema

    if not text or not text.strip():
        raise ValueError("message text is required")
    if len(text) > 4096:
        raise ValueError("message text exceeds Telegram limit")
    if not _signal_owned(con, tenant_id=tenant_id, signal_id=signal_id):
        raise LookupError("signal not found")

    init_signal_domain_schema(con)
    key = destination_key.strip().upper()
    existing = _existing_publication(
        con, tenant_id=tenant_id, signal_id=signal_id, destination_key=key
    )
    if existing is not None:
        raise FileExistsError("signal already published to destination")

    destination = resolve_destination(con, tenant_id=tenant_id, destination_key=key)
    if destination is None:
        raise LookupError("Telegram destination not found or inactive")

    connection = get_connection_private(
        con, tenant_id=tenant_id, connection_id=int(destination["connection_id"])
    )
    if connection.get("status") != "ACTIVE" or not connection.get("secret_ref"):
        raise RuntimeError("Telegram connection is not publish-ready")

    token = load_secret(
        con,
        tenant_id=tenant_id,
        secret_ref=str(connection["secret_ref"]),
    )
    payload: dict[str, Any] = {
        "chat_id": str(destination["chat_id"]),
        "text": text.strip(),
    }
    if destination.get("thread_id") is not None:
        payload["message_thread_id"] = int(destination["thread_id"])

    own_client = client is None
    session = client or httpx.Client(timeout=timeout_seconds)
    try:
        response = session.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=payload,
        )
        if response.status_code != 200:
            raise RuntimeError("Telegram publish failed")
        body = response.json()
        result = body.get("result") if isinstance(body, dict) else None
        if not body.get("ok") or not isinstance(result, dict) or result.get("message_id") is None:
            raise RuntimeError("Telegram publish failed")
        message_id = int(result["message_id"])
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        publication_id = record_publication_receipt(
            con,
            tenant_id=tenant_id,
            signal_id=signal_id,
            destination_key=key,
            chat_id=str(destination["chat_id"]),
            message_id=message_id,
            published_at=now,
        )
        return {
            "ok": True,
            "publication_id": publication_id,
            "signal_id": signal_id,
            "destination_key": key,
            "chat_id": str(destination["chat_id"]),
            "message_id": message_id,
        }
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError("Telegram publish failed") from exc
    finally:
        if own_client:
            session.close()
