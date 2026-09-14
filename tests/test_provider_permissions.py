from __future__ import annotations

import pytest

from app.provider_permissions import ProviderPermission, require_permission
from app.tenancy import TenantContext, TenantRole


def _ctx(role: TenantRole) -> TenantContext:
    return TenantContext(tenant_id=1, user_id=10, role=role)


def test_owner_can_manage_billing_telegram_and_branding() -> None:
    require_permission(_ctx(TenantRole.OWNER), ProviderPermission.MANAGE_BILLING)
    require_permission(_ctx(TenantRole.OWNER), ProviderPermission.MANAGE_TELEGRAM)
    require_permission(_ctx(TenantRole.OWNER), ProviderPermission.MANAGE_BRANDING)


def test_admin_can_manage_telegram_and_branding_but_not_billing() -> None:
    require_permission(_ctx(TenantRole.ADMIN), ProviderPermission.MANAGE_TELEGRAM)
    require_permission(_ctx(TenantRole.ADMIN), ProviderPermission.MANAGE_BRANDING)
    with pytest.raises(PermissionError):
        require_permission(_ctx(TenantRole.ADMIN), ProviderPermission.MANAGE_BILLING)


def test_publisher_can_publish_but_cannot_change_tenant_configuration() -> None:
    require_permission(_ctx(TenantRole.PUBLISHER), ProviderPermission.PUBLISH_SIGNAL)
    for permission in (ProviderPermission.MANAGE_TELEGRAM, ProviderPermission.MANAGE_BRANDING):
        with pytest.raises(PermissionError):
            require_permission(_ctx(TenantRole.PUBLISHER), permission)


def test_viewer_is_read_only() -> None:
    require_permission(_ctx(TenantRole.VIEWER), ProviderPermission.VIEW)
    for permission in (
        ProviderPermission.PUBLISH_SIGNAL,
        ProviderPermission.MANAGE_TELEGRAM,
        ProviderPermission.MANAGE_MEMBERS,
        ProviderPermission.MANAGE_BILLING,
        ProviderPermission.MANAGE_BRANDING,
    ):
        with pytest.raises(PermissionError):
            require_permission(_ctx(TenantRole.VIEWER), permission)
