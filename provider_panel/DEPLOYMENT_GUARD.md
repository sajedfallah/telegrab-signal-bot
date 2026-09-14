# Deployment Guard

This branch is safe for source review and local UI preview. It is not approved for production route exposure yet.

Production enablement requires all of:
- Phase 1 tenant migration validated on a copy of the production DB and then deployed safely.
- Provider authentication and TenantMembership/RBAC enforced.
- Tenant-scoped APIs implemented and isolation tests passing.
- Demo fixtures removed from production data path.
- Telegram/MT5/license/credit truth sourced from backend systems.
- Visual acceptance completed against the approved UI.

Existing NEXUS Mini App and production runtime must remain untouched until those gates pass.