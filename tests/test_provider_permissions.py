from __future__ import annotations

import pytest

from app.provider_permissions import ProviderPermission, require_permission
from app.tenancy import TenantContext, TenantRole


def _ctx(role: TenantRole) -> TenantContext:
    return TenantContext(tenant_id=1, user_id=10, role=role)


def test_owner_can_manage_billing_and_telegram() -> None:
    require_permission(_ctx(TenantRole.OWNER), ProviderPermission.MANAGE_BILLING)
    require_permission(_ctx(TenantRole.OWNER), ProviderPermission.MANAGE_TELEGRAM)


def test_admin_can_manage_telegram_but_not_billing() -> None:
    require_permission(_ctx(TenantRole.ADMIN), ProviderPermission.MANAGE_TELEGRAM)
    with pytest.raises(PermissionError):
        require_permission(_ctx(TenantRole.ADMIN), ProviderPermission.MANAGE_BILLING)


def test_publisher_can_publish_but_cannot_change_telegram_routing() -> None:
    require_permission(_ctx(TenantRole.PUBLISHER), ProviderPermission.PUBLISH_SIGNAL)
    with pytest.raises(PermissionError):
        require_permission(_ctx(TenantRole.PUBLISHER), ProviderPermission.MANAGE_TELEGRAM)


def test_viewer_is_read_only() -> None:
    require_permission(_ctx(TenantRole.VIEWER), ProviderPermission.VIEW)
    for permission in (ProviderPermission.PUBLISH_SIGNAL, ProviderPermission.MANAGE_TELEGRAM, ProviderPermission.MANAGE_MEMBERS, ProviderPermission.MANAGE_BILLING):
        with pytest.raises(PermissionError):
            require_permission(_ctx(TenantRole.VIEWER), permission)
