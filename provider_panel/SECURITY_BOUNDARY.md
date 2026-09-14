# Provider Panel Security Boundary

The UI may select a tenant/workspace only as a resource selector. It is never an authorization source.

Production requirements before route exposure:
- Resolve authenticated user server-side.
- Resolve TenantMembership server-side.
- Enforce RBAC per endpoint/action.
- Every provider-owned query filters/validates tenant ownership.
- Cross-tenant resource IDs return 403/404 without leaking existence/details.
- Telegram/MT5/API credentials never reach client responses after save.
- Sensitive actions are audit logged.
- Copy Trade credit/license enforcement is server-side and atomic.
- Provider UI never receives platform Super Admin controls.

The current static preview intentionally has no live credentials or production mutations.