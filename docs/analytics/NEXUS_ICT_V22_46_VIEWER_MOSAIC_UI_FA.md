# NEXUS Analytics Viewer V22.46 — Mosaic-style UI

UI architecture is based on the dashboard layout and UI patterns of Mosaic Lite by Cruip:
https://github.com/cruip/tailwind-dashboard-template

The upstream README states Mosaic Lite is released under GPL-3.0.

## Viewer sections
- Overview
- Signal Lab
- CE Lab
- Sequence Lab
- Timing Lab
- Execution Lab
- Management Lab
- Data Quality

## UI elements used
- fixed dashboard sidebar
- sticky top header
- KPI cards
- 12-column responsive dashboard grid
- chart cards
- recent activity feed
- data tables
- dark mode
- mobile sidebar behavior

## Data sources
Viewer reads MT5 Common Files and supports historical V22 analytics plus V22.46 research datasets.

## License boundary
A Mosaic/Cruip GPL notice is included in the standalone Analytics Viewer package.
The private MQL5 Expert Advisor remains a separate component and is not copied from Mosaic.
