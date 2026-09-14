# NEXUS Provider Panel UI v1

Approved visual implementation target for the multi-tenant Provider Panel.

## Visual contract

The approved design is a UI contract, not loose inspiration. The implementation retains the dashboard density and visual elements from the approved mockup: KPI cards, line/area charts, donut chart, data tables, health indicators, quick actions, responsive layout, Signal Center, Copy Trade, Subscribers, Reports, Branding and Settings.

## Architecture boundary

This directory is intentionally separate from `miniapp/`. The existing NEXUS customer Mini App remains untouched. Provider Panel is a B2B workspace and must not replace the consumer Mini App.

Current UI uses deterministic fixture data so all approved components are visible before backend contracts are wired. Fixtures are presentation-only and must never be represented as live trading/business data.

## Next integration contracts

- Provider identity: Tenant + TenantMembership + RBAC.
- Dashboard KPIs: tenant-scoped aggregate API.
- Signal Center: tenant-scoped Signal/SignalPublication/SignalEvent APIs.
- Copy Trade: tenant-scoped Customer/RetailPlan/CopyLicense/Credit APIs.
- Reports: tenant-scoped metrics API.
- Branding: BrandAsset and tenant appearance settings.
- Settings health: TelegramConnection, TradingConnection, subscription and license-service health.

## Acceptance rule

No approved chart/table/KPI/health component may be removed merely to simplify implementation. When a backend API is unavailable, retain the component with an explicit loading/empty/fixture state until the real tenant-scoped data contract is connected.