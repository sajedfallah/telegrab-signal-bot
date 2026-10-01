from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Iterable


NEXUS_TENANT_SLUG = "nexus"
NEXUS_TENANT_NAME = "NEXUS"


class TenantStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"


class TenantRole(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    ANALYST = "ANALYST"
    PUBLISHER = "PUBLISHER"
    VIEWER = "VIEWER"


ROLE_RANK = {
    TenantRole.VIEWER: 10,
    TenantRole.PUBLISHER: 20,
    TenantRole.ANALYST: 30,
    TenantRole.ADMIN: 40,
    TenantRole.OWNER: 50,
}


@dataclass(frozen=True)
class TenantContext:
    tenant_id: int
    user_id: int
    role: TenantRole

    def require(self, *roles: TenantRole) -> None:
        if self.role not in roles:
            raise PermissionError("tenant role is not authorized for this operation")

    def require_at_least(self, role: TenantRole) -> None:
        if ROLE_RANK[self.role] < ROLE_RANK[role]:
            raise PermissionError("tenant role is not authorized for this operation")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_tenant_schema(con: sqlite3.Connection) -> int:
    """Create the additive Phase-1 tenant/RBAC schema and return NEXUS tenant id.

    This migration is deliberately additive and idempotent. It does not alter legacy
    ownership yet, so existing NEXUS runtime behavior remains compatible while the
    domains are migrated one-by-one.
    """
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            business_name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE'
                CHECK(status IN ('ACTIVE','SUSPENDED','CANCELLED')),
            timezone TEXT NOT NULL DEFAULT 'UTC',
            locale TEXT NOT NULL DEFAULT 'en',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tenant_memberships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL
                CHECK(role IN ('OWNER','ADMIN','ANALYST','PUBLISHER','VIEWER')),
            status TEXT NOT NULL DEFAULT 'ACTIVE'
                CHECK(status IN ('ACTIVE','SUSPENDED')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(tenant_id,user_id),
            FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_tenant_memberships_user
            ON tenant_memberships(user_id,status);
        CREATE INDEX IF NOT EXISTS idx_tenant_memberships_tenant_role
            ON tenant_memberships(tenant_id,role,status);
        """
    )
    now = _now_iso()
    con.execute(
        """
        INSERT INTO tenants(slug,business_name,display_name,status,timezone,locale,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(slug) DO NOTHING
        """,
        (NEXUS_TENANT_SLUG, NEXUS_TENANT_NAME, NEXUS_TENANT_NAME, "ACTIVE", "UTC", "en", now, now),
    )
    row = con.execute("SELECT id FROM tenants WHERE slug=?", (NEXUS_TENANT_SLUG,)).fetchone()
    if row is None:
        raise RuntimeError("failed to create/resolve NEXUS tenant")
    return int(row[0])


def grant_membership(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    user_id: int,
    role: TenantRole,
) -> None:
    now = _now_iso()
    con.execute(
        """
        INSERT INTO tenant_memberships(tenant_id,user_id,role,status,created_at,updated_at)
        VALUES(?,?,?,'ACTIVE',?,?)
        ON CONFLICT(tenant_id,user_id) DO UPDATE SET
            role=excluded.role,
            status='ACTIVE',
            updated_at=excluded.updated_at
        """,
        (tenant_id, user_id, role.value, now, now),
    )


def bootstrap_nexus_admins(con: sqlite3.Connection, admin_ids: Iterable[int]) -> int:
    """Attach existing Telegram admins to NEXUS as OWNER without creating users.

    Only IDs already present in users are attached, preserving FK integrity and
    avoiding synthetic customer records.
    """
    tenant_id = init_tenant_schema(con)
    for user_id in {int(v) for v in admin_ids}:
        exists = con.execute("SELECT 1 FROM users WHERE telegram_id=?", (user_id,)).fetchone()
        if exists:
            grant_membership(con, tenant_id=tenant_id, user_id=user_id, role=TenantRole.OWNER)
    return tenant_id


def resolve_tenant_context(
    con: sqlite3.Connection,
    *,
    user_id: int,
    tenant_id: int,
) -> TenantContext:
    """Resolve tenant authorization from server-side membership state.

    Callers must not treat a client-supplied tenant_id as authorization. The ID is
    only a resource selector; membership is always verified here.
    """
    row = con.execute(
        """
        SELECT tm.tenant_id,tm.user_id,tm.role
        FROM tenant_memberships tm
        JOIN tenants t ON t.id=tm.tenant_id
        WHERE tm.tenant_id=? AND tm.user_id=?
          AND tm.status='ACTIVE' AND t.status='ACTIVE'
        """,
        (tenant_id, user_id),
    ).fetchone()
    if row is None:
        raise PermissionError("tenant membership not found or inactive")
    return TenantContext(
        tenant_id=int(row[0]),
        user_id=int(row[1]),
        role=TenantRole(str(row[2])),
    )


def assert_tenant_resource(
    con: sqlite3.Connection,
    *,
    table: str,
    resource_id: int,
    tenant_id: int,
) -> None:
    """Guard a tenant-owned row after that table has received tenant_id.

    Table names cannot be bound parameters, therefore this helper intentionally
    accepts only a fixed allow-list. Extend it as domains become tenant-aware.
    """
    allowed = {
        "signals",
        "payments",
        "licenses",
        "subscriptions",
        "autotrade_mt5_accounts",
        "autotrade_exchange_accounts",
        "autotrade_trade_executions",
    }
    if table not in allowed:
        raise ValueError("table is not approved for tenant resource checks")
    row = con.execute(
        f"SELECT 1 FROM {table} WHERE id=? AND tenant_id=?",
        (resource_id, tenant_id),
    ).fetchone()
    if row is None:
        raise LookupError("resource not found")
