# Provider Panel V1 — Visual Acceptance Contract

Status: APPROVED

The approved UI is a visual implementation contract, not inspiration. Production implementation must not simplify away charts, KPI cards, tables, health indicators, navigation, branding preview, or responsive behavior.

## Required pages

1. Dashboard
   - 4 KPI cards: Active Subscribers, Monthly Revenue, Total Signals, Win Rate
   - Revenue Overview line/area chart
   - Signal Distribution donut chart + legend
   - Recent Signals table
   - Quick Actions
   - Telegram / MT5 / Copy Trade / Subscription health strip
2. Signal Center
   - New Signal CTA
   - status filters + symbol/status selectors
   - signal lifecycle table
3. Copy Trade
   - Active Copiers / Available Credits / Retail Revenue / Gross Margin KPIs
   - copier growth chart
   - prepaid capacity panel
4. Subscribers
   - customer/access table
5. Reports & Analytics
   - Revenue / Signals / Win Rate / Avg R:R KPIs
   - P&L visualization
6. Settings & Branding
   - logo + favicon assets
   - brand color controls
   - live brand preview
7. Settings
   - Telegram, MT5, Signal Center subscription, Copy Trade infrastructure health

## Visual rules

- Desktop: fixed dark navy sidebar + light content surface.
- Primary accent: blue; green/red reserved for positive/negative status semantics.
- Cards retain border, radius, shadow, hierarchy, and spacing from the approved mockup.
- Charts are real rendered components/canvas, never screenshots or omitted placeholders.
- Tables remain horizontally scrollable on narrow screens.
- Mobile keeps core navigation and responsive KPI/content grids.
- Loading, empty, error and disconnected states must preserve layout rather than collapsing components.

## Data policy

Current static preview may use fixtures. Fixture values must never be represented as live production data. Backend integration replaces fixture sources without redesigning components.

## Isolation policy

This panel is separate from `miniapp/`. Existing NEXUS customer Mini App must not be rewritten or replaced by Provider Panel work.

## Acceptance gate

A page is UI Complete only when:

- all approved components exist;
- charts/tables/KPIs are present and responsive;
- no major component was simplified away;
- desktop and mobile layouts remain usable;
- fixture/live-data state is explicit;
- visual review has passed before backend integration/deployment.
