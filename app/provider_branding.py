from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import Any


_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_branding_schema(con: sqlite3.Connection) -> None:
    con.execute(
        """CREATE TABLE IF NOT EXISTS provider_branding(
            tenant_id INTEGER PRIMARY KEY,
            brand_name TEXT,
            tagline TEXT,
            primary_color TEXT NOT NULL DEFAULT '#2F72FF',
            secondary_color TEXT NOT NULL DEFAULT '#14C9B7',
            accent_color TEXT NOT NULL DEFAULT '#FFAD32',
            background_color TEXT NOT NULL DEFAULT '#07172A',
            logo_url TEXT,
            favicon_url TEXT,
            updated_by_user_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )"""
    )


def _table_exists(con: sqlite3.Connection) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='provider_branding'"
    ).fetchone() is not None


def _clean_text(value: str | None, *, max_length: int) -> str | None:
    cleaned = (value or "").strip()
    if len(cleaned) > max_length:
        raise ValueError("branding text is too long")
    return cleaned or None


def _color(value: str | None, fallback: str) -> str:
    normalized = (value or fallback).strip().upper()
    if not _HEX_COLOR.fullmatch(normalized):
        raise ValueError("branding colors must use #RRGGBB format")
    return normalized


def _asset_url(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    if len(cleaned) > 1000:
        raise ValueError("branding asset URL is too long")
    if not (cleaned.startswith("https://") or cleaned.startswith("http://") or cleaned.startswith("/")):
        raise ValueError("branding asset URL must be http(s) or an absolute application path")
    return cleaned


def get_branding(con: sqlite3.Connection, *, tenant_id: int) -> dict[str, Any]:
    tenant = con.execute(
        "SELECT display_name,business_name FROM tenants WHERE id=?", (tenant_id,)
    ).fetchone()
    if tenant is None:
        raise LookupError("tenant not found")
    defaults = {
        "tenant_id": tenant_id,
        "brand_name": str(tenant["display_name"] or tenant["business_name"] or "Provider"),
        "tagline": None,
        "primary_color": "#2F72FF",
        "secondary_color": "#14C9B7",
        "accent_color": "#FFAD32",
        "background_color": "#07172A",
        "logo_url": None,
        "favicon_url": None,
        "status": "unavailable" if not _table_exists(con) else "default",
        "updated_at": None,
    }
    if not _table_exists(con):
        return defaults
    row = con.execute(
        "SELECT brand_name,tagline,primary_color,secondary_color,accent_color,background_color,logo_url,favicon_url,updated_at "
        "FROM provider_branding WHERE tenant_id=?",
        (tenant_id,),
    ).fetchone()
    if row is None:
        return defaults
    data = dict(row)
    data["tenant_id"] = tenant_id
    data["brand_name"] = data.get("brand_name") or defaults["brand_name"]
    data["status"] = "ready"
    return data


def save_branding(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    updated_by_user_id: int,
    brand_name: str | None = None,
    tagline: str | None = None,
    primary_color: str | None = None,
    secondary_color: str | None = None,
    accent_color: str | None = None,
    background_color: str | None = None,
    logo_url: str | None = None,
    favicon_url: str | None = None,
) -> dict[str, Any]:
    init_branding_schema(con)
    current = get_branding(con, tenant_id=tenant_id)
    values = {
        "brand_name": _clean_text(brand_name if brand_name is not None else current.get("brand_name"), max_length=160),
        "tagline": _clean_text(tagline if tagline is not None else current.get("tagline"), max_length=240),
        "primary_color": _color(primary_color, str(current.get("primary_color") or "#2F72FF")),
        "secondary_color": _color(secondary_color, str(current.get("secondary_color") or "#14C9B7")),
        "accent_color": _color(accent_color, str(current.get("accent_color") or "#FFAD32")),
        "background_color": _color(background_color, str(current.get("background_color") or "#07172A")),
        "logo_url": _asset_url(logo_url if logo_url is not None else current.get("logo_url")),
        "favicon_url": _asset_url(favicon_url if favicon_url is not None else current.get("favicon_url")),
    }
    now = _now()
    con.execute(
        "INSERT INTO provider_branding(tenant_id,brand_name,tagline,primary_color,secondary_color,accent_color,background_color,logo_url,favicon_url,updated_by_user_id,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(tenant_id) DO UPDATE SET brand_name=excluded.brand_name,tagline=excluded.tagline,"
        "primary_color=excluded.primary_color,secondary_color=excluded.secondary_color,accent_color=excluded.accent_color,"
        "background_color=excluded.background_color,logo_url=excluded.logo_url,favicon_url=excluded.favicon_url,"
        "updated_by_user_id=excluded.updated_by_user_id,updated_at=excluded.updated_at",
        (
            tenant_id,
            values["brand_name"],
            values["tagline"],
            values["primary_color"],
            values["secondary_color"],
            values["accent_color"],
            values["background_color"],
            values["logo_url"],
            values["favicon_url"],
            updated_by_user_id,
            now,
            now,
        ),
    )
    return get_branding(con, tenant_id=tenant_id)
