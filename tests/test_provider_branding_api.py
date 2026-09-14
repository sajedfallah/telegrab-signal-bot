from __future__ import annotations

import sqlite3

import pytest
from fastapi import HTTPException

from app.provider_branding_api import BrandingUpdateRequest, branding, update_branding
from app.tenancy import TenantContext, TenantRole, init_tenant_schema


class Conn:
    def __init__(self, path):
        self.path = path
    def __enter__(self):
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        return self.con
    def __exit__(self, exc_type, *_):
        if exc_type is None:
            self.con.commit()
        else:
            self.con.rollback()
        self.con.close()


def _prepare(tmp_path):
    path = tmp_path / "provider.db"
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE users(telegram_id INTEGER PRIMARY KEY)")
    tenant_id = int(init_tenant_schema(con))
    con.commit()
    con.close()
    return path, tenant_id


def test_owner_can_update_and_view_branding(monkeypatch, tmp_path):
    path, tenant_id = _prepare(tmp_path)
    monkeypatch.setattr("app.provider_branding_api.db.conn", lambda: Conn(path))
    monkeypatch.setattr(
        "app.provider_branding_api._tenant_context",
        lambda *_: TenantContext(tenant_id=tenant_id, user_id=1001, role=TenantRole.OWNER),
    )
    result = update_branding(
        BrandingUpdateRequest(brand_name="Alpha", primary_color="#123456"), "signed", tenant_id
    )
    assert result["branding"]["brand_name"] == "Alpha"
    assert result["branding"]["primary_color"] == "#123456"
    viewed = branding("signed", tenant_id)
    assert viewed["branding"]["brand_name"] == "Alpha"


def test_viewer_cannot_update_branding(monkeypatch, tmp_path):
    path, tenant_id = _prepare(tmp_path)
    monkeypatch.setattr("app.provider_branding_api.db.conn", lambda: Conn(path))
    monkeypatch.setattr(
        "app.provider_branding_api._tenant_context",
        lambda *_: TenantContext(tenant_id=tenant_id, user_id=1001, role=TenantRole.VIEWER),
    )
    with pytest.raises(HTTPException) as exc:
        update_branding(BrandingUpdateRequest(brand_name="Blocked"), "signed", tenant_id)
    assert exc.value.status_code == 403


def test_admin_can_update_branding(monkeypatch, tmp_path):
    path, tenant_id = _prepare(tmp_path)
    monkeypatch.setattr("app.provider_branding_api.db.conn", lambda: Conn(path))
    monkeypatch.setattr(
        "app.provider_branding_api._tenant_context",
        lambda *_: TenantContext(tenant_id=tenant_id, user_id=2002, role=TenantRole.ADMIN),
    )
    result = update_branding(BrandingUpdateRequest(tagline="Admin managed"), "signed", tenant_id)
    assert result["branding"]["tagline"] == "Admin managed"
