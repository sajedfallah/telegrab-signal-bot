# Next Implementation Gate

1. Run Provider Panel CI and visual preview.
2. Complete Phase 1 VPS tenant migration validation.
3. Wire authenticated Provider route shell to TenantContext/RBAC.
4. Implement read-only tenant-scoped dashboard/health endpoints first.
5. Replace Dashboard fixture values with live tenant-scoped data while retaining Loading/Empty/Error states.
6. Then wire Signal Center read/write and existing Telegram lifecycle.
7. Then wire Copy Trade Customer/License/Credit domain.
8. Visual screenshot comparison remains a release gate after each page integration.

Do not merge this branch into production solely because the static UI renders. Production exposure requires tenant isolation validation.