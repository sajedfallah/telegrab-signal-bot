# Integration Order

To reduce risk, wire the implemented UI in this order:

1. Provider authentication + TenantContext + RBAC.
2. Read-only Dashboard aggregates and Health.
3. Branding read/write and tenant-specific assets.
4. Signal Center read path.
5. Signal creation/publication path using existing NEXUS lifecycle engine generalized by tenant.
6. Signal lifecycle events/replies.
7. Subscribers/Customer domain.
8. Copy Trade License + Credit read path.
9. Atomic Copy Trade activation/renewal mutations.
10. Reports/Analytics aggregates.

Do not wire high-risk financial/license mutations before tenant isolation and read-only provider surfaces are validated.