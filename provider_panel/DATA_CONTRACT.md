# Provider Panel — Backend Data Contract v1

The UI is implemented first with fixture data. Backend integration must be tenant-scoped and server-authorized through TenantMembership/RBAC; the client must never gain authorization merely by submitting a tenant_id.

## Dashboard
`GET /provider/v1/dashboard`
Returns provider identity, KPI values/trends, revenue series, signal distribution, recent signals and integration health.

## Signal Center
`GET /provider/v1/signals`
`POST /provider/v1/signals`
`GET /provider/v1/signals/{signal_id}`
Lifecycle updates must preserve Signal -> SignalPublication -> Telegram reply behavior and validate tenant ownership server-side.

## Copy Trade
`GET /provider/v1/copy-trade/summary`
`GET /provider/v1/copy-trade/licenses`
`POST /provider/v1/copy-trade/licenses`
`POST /provider/v1/copy-trade/licenses/{license_id}/renew`
No-credit activation/renewal must be rejected server-side. Credit reservation/consumption must be atomic and idempotent.

## Subscribers
`GET /provider/v1/customers`
`POST /provider/v1/customers`
Customer, RetailPlan and CopyLicense data are always tenant-scoped.

## Reports
`GET /provider/v1/reports?range=30d`
Returns tenant-scoped KPI aggregates and ordered P&L/performance series. Never synthesize trading performance as live truth.

## Branding
`GET /provider/v1/branding`
`PUT /provider/v1/branding`
BrandAsset/logo/name/colors are tenant-specific. Existing NEXUS hard-coded branding must not leak into another provider.

## Settings / Health
`GET /provider/v1/health`
Returns Telegram, MT5/TradingConnection, subscription and Copy Trade/license-service health with last heartbeat/error metadata.

## UI states
Every data component retains Loading, Empty, Error and Ready states. Fixture/demo values are only for local visual development and must be visibly separated from production truth once APIs are wired.