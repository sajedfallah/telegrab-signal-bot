from __future__ import annotations

from enum import StrEnum

from .tenancy import TenantContext, TenantRole


class ProviderPermission(StrEnum):
    VIEW = "VIEW"
    MANAGE_TELEGRAM = "MANAGE_TELEGRAM"
    PUBLISH_SIGNAL = "PUBLISH_SIGNAL"
    MANAGE_MEMBERS = "MANAGE_MEMBERS"
    MANAGE_BILLING = "MANAGE_BILLING"


_PERMISSION_ROLES: dict[ProviderPermission, frozenset[TenantRole]] = {
    ProviderPermission.VIEW: frozenset(TenantRole),
    ProviderPermission.MANAGE_TELEGRAM: frozenset({TenantRole.OWNER, TenantRole.ADMIN}),
    ProviderPermission.PUBLISH_SIGNAL: frozenset({TenantRole.OWNER, TenantRole.ADMIN, TenantRole.ANALYST, TenantRole.PUBLISHER}),
    ProviderPermission.MANAGE_MEMBERS: frozenset({TenantRole.OWNER, TenantRole.ADMIN}),
    ProviderPermission.MANAGE_BILLING: frozenset({TenantRole.OWNER}),
}


def require_permission(ctx: TenantContext, permission: ProviderPermission) -> None:
    if ctx.role not in _PERMISSION_ROLES[permission]:
        raise PermissionError(f"tenant role is not authorized for {permission.value}")
