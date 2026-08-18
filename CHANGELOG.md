# Changelog

## 7.0.0 — Canonical baseline

First version designated as the maintained executable repository baseline.

### Added

- Signal Analytics Dashboard (7d/30d/all-time)
- analytics by symbol
- analytics by NEXUS trailing profile
- FREE vs VIP analytics
- subscription plan entitlements
- VIP/Auto-Trade license snapshots
- renewal discounts and upgrade-aware entitlement behavior
- paid/admin/trial license source tracking
- persistent SQLite FSM storage
- extracted FSM state module
- analytics and subscription routers
- analytics and license services

### Preserved from v6.5 lineage

- Persian/English UX
- public membership gate
- Rial/USDT payment flows
- referrals/NEXUS Points
- discounts/campaigns
- broadcast/CRM/backup/audit
- secure VIP access
- Signal Center with dynamic TP
- Forex lot / Crypto leverage
- NEXUS trailing profiles
- FREE/VIP/BOTH publication
- Break Even / Partial / Trailing / TP / SL updates
- close/result single-photo flow
- automatic admin/channel reports
- client entitlement-aware menu

### Validation

- compileall: pass
- unit/regression tests: 21/21 pass

See `BUILD_TEST_REPORT_V7_0.txt` for build-environment details.
