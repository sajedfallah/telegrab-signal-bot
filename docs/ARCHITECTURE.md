# Architecture — NEXUS v7.0

## Architecture status

v7.0 is intentionally a **hybrid modular architecture**. Stable legacy handlers remain in `app/main.py`, while new domains are extracted into routers/services/storage. This minimizes regression risk while providing a migration path away from the monolith.

## Runtime composition

```text
Telegram Bot API
      |
   aiogram
      |
+-------------------------------+
| Legacy Router / app/main.py   |
| - client flows                |
| - payment flows               |
| - admin flows                 |
| - signal publisher/lifecycle  |
| - workers/reports             |
+-------------------------------+
       |       |        |
       |       |        +------------------+
       |       |                           |
       v       v                           v
  app/db.py   Services                 New Routers
              - license_service        - analytics
              - analytics_service      - subscriptions
       |
       v
 SQLite nexus_bot.db

aiogram FSM <-> app/storage/sqlite_storage.py <-> SQLite nexus_fsm.db
```

## Module responsibilities

### `app/main.py`

Current stable integration layer. Owns many Telegram handlers and the existing business orchestration. It should gradually shrink, not be rewritten wholesale.

### `app/db.py`

Database bootstrap, migrations and current query/repository functions. SQLite is hardened with WAL/busy-timeout behavior in the v6.4+ lineage.

### `app/states.py`

Canonical FSM state declarations. Do not redeclare flow states inside routers.

### `app/storage/sqlite_storage.py`

Persistent aiogram FSM storage so ordinary restarts do not lose active payment/signal workflows.

### `app/services/license_service.py`

Business rules for plan entitlements, license activation/extension, paid/admin/trial source semantics, renewal and upgrade.

### `app/services/analytics_service.py`

Aggregates signal performance by range, symbol, trailing profile and destination/channel.

### `app/routers/analytics.py`

Admin-facing analytics router.

### `app/routers/subscriptions.py`

Admin-facing plan entitlement and renewal controls.

### `app/signals/calculator.py`

Pure calculation logic for risk/reward and direction-aware result calculations. This is high-value testable code and should remain independent of Telegram.

### `app/signals/card_generator.py`

NEXUS visual framing for chart images. Do not crop the source chart. Avoid adding large information cards when a caption already carries data.

## Data stores

### `nexus_bot.db`

Primary business data: users, subscriptions/licenses, payments, plans, referrals, discounts/campaigns, signals, signal updates, reports/audit and related state.

### `nexus_fsm.db`

Persistent aiogram conversation state/data. This DB is runtime-only and must not be committed.

## Database evolution

The project uses in-place migrations/backfills to preserve data from v6-era databases. Schema changes must be backward compatible whenever possible.

Rules:

1. Never drop production columns/tables as part of a normal feature migration.
2. Add columns with safe defaults.
3. Backfill existing licenses/plan entitlements to preserve old behavior.
4. Add a regression test for every migration with business impact.

## Background workers

The stable core includes recurring work for:

- license expiration/reminders
- database backups
- automatic daily/weekly reporting

Network-heavy or CPU-heavy tasks should continue moving off the main event loop over time.

## Future architecture target

Long-term target:

```text
app/
  core/
  handlers/ or routers/
    client.py
    payments.py
    admin.py
    signals.py
    reports.py
  services/
  repositories/
  models/
  workers/
  storage/
```

This migration should be incremental. Production behavior takes priority over aesthetic refactoring.
