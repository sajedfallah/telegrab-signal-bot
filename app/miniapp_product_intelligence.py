from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from . import db
from .config import settings
from .miniapp_api import _auth_user, _entitlements

router = APIRouter(prefix="/miniapp/api", tags=["NEXUS Mini App Product Intelligence"])

ALLOWED_EVENTS = {
    "miniapp_open",
    "home_view",
    "home_cta",
    "signal_filter",
    "signal_detail",
    "performance_view",
    "pricing_view",
    "product_card_viewed",
    "product_swipe",
    "product_selected",
    "checkout_start",
    "account_view",
    "trades_view",
    "trade_detail_view",
    "content_open",
    "notification_open",
}
CONTENT_TYPES = {"market_insight", "academy"}
AUDIENCES = {"ALL", "GUEST", "VIP", "AUTOTRADE", "BUNDLE", "EXPIRING", "EXPIRED"}


class EventIn(BaseModel):
    event_name: str = Field(min_length=1, max_length=64)
    route: str | None = Field(default=None, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContentIn(BaseModel):
    content_type: str = Field(min_length=1, max_length=32)
    title_fa: str = Field(min_length=1, max_length=160)
    body_fa: str | None = Field(default=None, max_length=900)
    cta_fa: str | None = Field(default=None, max_length=80)
    destination: str | None = Field(default=None, max_length=64)
    url: str | None = Field(default=None, max_length=500)
    audience: str = Field(default="ALL", max_length=32)
    priority: int = Field(default=100, ge=0, le=1000)
    starts_at: str | None = None
    ends_at: str | None = None
    active: bool = True


class ContentStateIn(BaseModel):
    active: bool


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_schema() -> None:
    with db.conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS miniapp_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                event_name TEXT NOT NULL,
                route TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_miniapp_events_user_time
                ON miniapp_events(telegram_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_miniapp_events_name_time
                ON miniapp_events(event_name, created_at);

            CREATE TABLE IF NOT EXISTS miniapp_content (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_type TEXT NOT NULL,
                title_fa TEXT NOT NULL,
                body_fa TEXT,
                cta_fa TEXT,
                destination TEXT,
                url TEXT,
                audience TEXT NOT NULL DEFAULT 'ALL',
                priority INTEGER NOT NULL DEFAULT 100,
                active INTEGER NOT NULL DEFAULT 1,
                starts_at TEXT,
                ends_at TEXT,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_miniapp_content_active
                ON miniapp_content(active, content_type, priority, starts_at, ends_at);

            CREATE TABLE IF NOT EXISTS miniapp_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                kind TEXT NOT NULL DEFAULT 'SYSTEM',
                title_fa TEXT NOT NULL,
                body_fa TEXT,
                destination TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_miniapp_notifications_user_time
                ON miniapp_notifications(telegram_id, created_at);

            CREATE TABLE IF NOT EXISTS miniapp_notification_reads (
                telegram_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                source_id INTEGER NOT NULL,
                read_at TEXT NOT NULL,
                PRIMARY KEY(telegram_id, source, source_id)
            );
            """
        )


def _parse_iso(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_metadata(value: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, raw in list(value.items())[:12]:
        name = str(key)[:64]
        if raw is None or isinstance(raw, (bool, int, float)):
            result[name] = raw
        elif isinstance(raw, str):
            result[name] = raw[:256]
        elif isinstance(raw, (list, tuple)):
            result[name] = [str(item)[:80] for item in list(raw)[:10]]
        else:
            result[name] = str(raw)[:256]
    return result


def _experience_for(uid: int) -> dict[str, Any]:
    # Local import avoids a module cycle with miniapp_home, which consumes
    # home_content() while building the same experience payload.
    from .miniapp_experience import build_experience_context

    ent = _entitlements(uid)
    latest = db.latest_license(uid)
    return build_experience_context(ent, dict(latest) if latest is not None else None)


def _audience_matches(audience: str, experience: dict[str, Any]) -> bool:
    key = str(audience or "ALL").upper()
    return key == "ALL" or key == str(experience.get("segment") or "GUEST").upper() or key == str(experience.get("lifecycle") or "GUEST").upper()


def home_content(experience: dict[str, Any]) -> dict[str, dict[str, Any] | None]:
    """Return only admin-authored, currently active Home content.

    There is intentionally no synthetic market insight fallback. If no current
    record exists, the customer UI hides the section rather than fabricating a
    market view or analysis.
    """
    _ensure_schema()
    now = datetime.now(timezone.utc)
    selected: dict[str, dict[str, Any] | None] = {"market_insight": None, "academy": None}
    with db.conn() as con:
        rows = con.execute(
            """
            SELECT id,content_type,title_fa,body_fa,cta_fa,destination,url,audience,priority,starts_at,ends_at
            FROM miniapp_content
            WHERE active=1 AND content_type IN ('market_insight','academy')
            ORDER BY priority DESC,id DESC
            """
        ).fetchall()
    for raw in rows:
        item = dict(raw)
        kind = str(item.get("content_type") or "").lower()
        if kind not in selected or selected[kind] is not None:
            continue
        if not _audience_matches(str(item.get("audience") or "ALL"), experience):
            continue
        starts = _parse_iso(item.get("starts_at"))
        ends = _parse_iso(item.get("ends_at"))
        if starts and now < starts:
            continue
        if ends and now >= ends:
            continue
        selected[kind] = item
    return selected


def _require_admin(init_data: str | None) -> int:
    uid = int(_auth_user(init_data)["id"])
    if uid not in settings.admin_ids:
        raise HTTPException(status_code=403, detail="admin access required")
    return uid


def _notification_label(event_type: str) -> str:
    key = str(event_type or "AUTOTRADE").upper()
    labels = {
        "EXECUTED": "اجرای AutoTrade",
        "CLOSED": "معامله بسته شد",
        "ERROR": "خطای AutoTrade",
        "REJECTED": "اجرای معامله رد شد",
        "PARTIAL_CLOSE": "بخشی از معامله بسته شد",
        "SL_UPDATE": "حد ضرر بروزرسانی شد",
        "TP_UPDATE": "حد سود بروزرسانی شد",
    }
    return labels.get(key, "رویداد AutoTrade")


def _notification_body(payload: Any) -> str | None:
    try:
        obj = json.loads(str(payload or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    for key in ("message", "detail_fa", "reason", "error_text", "status"):
        value = obj.get(key)
        if value:
            return str(value)[:500]
    return None


@router.post("/events")
def event(
    payload: EventIn,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    name = payload.event_name.strip().lower()
    if name not in ALLOWED_EVENTS:
        raise HTTPException(status_code=400, detail="unsupported analytics event")
    _ensure_schema()
    metadata = _safe_metadata(payload.metadata)
    with db.conn() as con:
        con.execute(
            "INSERT INTO miniapp_events(telegram_id,event_name,route,metadata_json,created_at) VALUES(?,?,?,?,?)",
            (uid, name, (payload.route or "")[:64] or None, json.dumps(metadata, ensure_ascii=False, separators=(",", ":")), _now()),
        )
    return {"ok": True}


@router.get("/content/home")
def customer_home_content(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    return home_content(_experience_for(uid))


@router.get("/notifications")
def notifications(
    limit: int = Query(default=30, ge=1, le=100),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    _ensure_schema()
    items: list[dict[str, Any]] = []
    with db.conn() as con:
        authored = con.execute(
            """
            SELECT n.id,n.kind,n.title_fa,n.body_fa,n.destination,n.created_at,
                   CASE WHEN r.read_at IS NULL THEN 0 ELSE 1 END AS is_read
            FROM miniapp_notifications n
            LEFT JOIN miniapp_notification_reads r
              ON r.telegram_id=n.telegram_id AND r.source='miniapp' AND r.source_id=n.id
            WHERE n.telegram_id=?
            ORDER BY n.id DESC LIMIT ?
            """,
            (uid, limit),
        ).fetchall()
        for row in authored:
            item = dict(row)
            items.append({"source": "miniapp", **item, "is_read": bool(item.get("is_read"))})

        auto_rows = con.execute(
            """
            SELECT n.id,n.event_type,n.payload_json,n.created_at,
                   CASE WHEN r.read_at IS NULL THEN 0 ELSE 1 END AS is_read
            FROM autotrade_notifications n
            LEFT JOIN miniapp_notification_reads r
              ON r.telegram_id=n.telegram_id AND r.source='autotrade' AND r.source_id=n.id
            WHERE n.telegram_id=?
            ORDER BY n.id DESC LIMIT ?
            """,
            (uid, limit),
        ).fetchall()
        for row in auto_rows:
            item = dict(row)
            items.append({
                "source": "autotrade",
                "id": int(item["id"]),
                "kind": str(item.get("event_type") or "AUTOTRADE"),
                "title_fa": _notification_label(str(item.get("event_type") or "")),
                "body_fa": _notification_body(item.get("payload_json")),
                "destination": "trades",
                "created_at": item.get("created_at"),
                "is_read": bool(item.get("is_read")),
            })
    items.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    items = items[:limit]
    return {"items": items, "unread_count": sum(1 for item in items if not item.get("is_read"))}


@router.post("/notifications/{source}/{notification_id}/read")
def notification_read(
    source: str,
    notification_id: int,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    source_key = str(source or "").lower()
    if source_key not in {"miniapp", "autotrade"}:
        raise HTTPException(status_code=400, detail="unsupported notification source")
    _ensure_schema()
    with db.conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO miniapp_notification_reads(telegram_id,source,source_id,read_at) VALUES(?,?,?,?)",
            (uid, source_key, notification_id, _now()),
        )
    return {"ok": True}


@router.get("/admin/content")
def admin_content(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    _require_admin(x_telegram_init_data)
    _ensure_schema()
    with db.conn() as con:
        rows = con.execute("SELECT * FROM miniapp_content ORDER BY active DESC,priority DESC,id DESC").fetchall()
    return {"items": [dict(row) for row in rows]}


@router.post("/admin/content")
def admin_content_create(
    payload: ContentIn,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    uid = _require_admin(x_telegram_init_data)
    kind = payload.content_type.strip().lower()
    audience = payload.audience.strip().upper()
    if kind not in CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="unsupported content type")
    if audience not in AUDIENCES:
        raise HTTPException(status_code=400, detail="unsupported content audience")
    _ensure_schema()
    now = _now()
    with db.conn() as con:
        cur = con.execute(
            """
            INSERT INTO miniapp_content(
                content_type,title_fa,body_fa,cta_fa,destination,url,audience,priority,active,
                starts_at,ends_at,created_by,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                kind, payload.title_fa.strip(), payload.body_fa, payload.cta_fa, payload.destination,
                payload.url, audience, payload.priority, 1 if payload.active else 0,
                payload.starts_at, payload.ends_at, uid, now, now,
            ),
        )
        content_id = int(cur.lastrowid)
    return {"ok": True, "id": content_id}


@router.post("/admin/content/{content_id}/state")
def admin_content_state(
    content_id: int,
    payload: ContentStateIn,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    _require_admin(x_telegram_init_data)
    _ensure_schema()
    with db.conn() as con:
        cur = con.execute(
            "UPDATE miniapp_content SET active=?,updated_at=? WHERE id=?",
            (1 if payload.active else 0, _now(), content_id),
        )
        if cur.rowcount < 1:
            raise HTTPException(status_code=404, detail="content not found")
    return {"ok": True, "active": payload.active}
