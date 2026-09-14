from __future__ import annotations

import sqlite3

import pytest

from app.provider_branding import get_branding, init_branding_schema, save_branding
from app.tenancy import init_tenant_schema


def _db():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE users(telegram_id INTEGER PRIMARY KEY)")
    tenant_id = int(init_tenant_schema(con))
    other_id = con.execute(
        "INSERT INTO tenants(slug,business_name,display_name,status,timezone,locale,created_at,updated_at) "
        "VALUES('other','Other LLC','Other Brand','ACTIVE','UTC','en','x','x') RETURNING id"
    ).fetchone()[0]
    return con, tenant_id, int(other_id)


def test_branding_defaults_and_tenant_isolation():
    con, tenant_id, other_id = _db()
    init_branding_schema(con)
    first = get_branding(con, tenant_id=tenant_id)
    assert first["status"] == "default"
    assert first["primary_color"] == "#2F72FF"

    saved = save_branding(
        con,
        tenant_id=tenant_id,
        updated_by_user_id=1001,
        brand_name="NEXUS Signals",
        tagline="Trade Smarter",
        primary_color="#112233",
        logo_url="https://cdn.example.com/nexus.png",
    )
    assert saved["status"] == "ready"
    assert saved["brand_name"] == "NEXUS Signals"
    assert saved["primary_color"] == "#112233"

    other = get_branding(con, tenant_id=other_id)
    assert other["status"] == "default"
    assert other["brand_name"] == "Other Brand"
    assert other["logo_url"] is None


def test_branding_validates_colors_and_asset_urls():
    con, tenant_id, _ = _db()
    with pytest.raises(ValueError):
        save_branding(con, tenant_id=tenant_id, updated_by_user_id=1, primary_color="blue")
    with pytest.raises(ValueError):
        save_branding(con, tenant_id=tenant_id, updated_by_user_id=1, logo_url="javascript:alert(1)")
