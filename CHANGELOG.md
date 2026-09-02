# Changelog

All notable repository changes are documented here. Releases follow Semantic Versioning.

## [7.1.0] — 2026-08-30

### Documentation and repository engineering

- Rewrote the root README with installation, configuration, architecture, testing, troubleshooting and security guidance.
- Added pinned runtime and development dependency manifests.
- Standardized `.env.example` with documented configuration categories and secret-handling guidance.
- Added MIT license.
- Added contribution guide and Code of Conduct.
- Added GitHub issue templates and pull-request checklist.
- Added GitHub Actions CI for compile checks, pytest/coverage, Black, Flake8 and dependency consistency.
- Added Dockerfile and Docker Compose deployment scaffolding.
- Hardened `.gitignore` against databases, logs, environments, caches and build artifacts.
- Standardized release metadata on `VERSION=7.1.0`.

### Compatibility note

This release is a repository/documentation and developer-experience release. It does not claim new production trading execution behavior that is not already implemented and tested by the application source. The historical v7 baseline explicitly separates the prepared AutoTrade entitlement layer from real AutoTrade execution. 

## [7.0.6]

### Existing baseline

- Latest tested AutoTrade milestone recorded by the existing repository history.
- Signal analytics, entitlement/license, persistent FSM and administrative improvements from the 7.0 line.

## [7.0.0]

### Canonical baseline

- First maintained executable repository baseline.
- Signal Analytics Dashboard.
- Subscription plan entitlements and VIP/Auto-Trade license snapshots.
- Persistent SQLite FSM storage.
- Extracted analytics/subscription routers and services.
- Preserved payment, referral, signal publication, reporting and administration flows.

For earlier historical development, consult the project-history documentation.
