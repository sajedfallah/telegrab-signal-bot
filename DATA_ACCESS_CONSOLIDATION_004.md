# DATA-ACCESS-CONSOLIDATION-004 — Closure Audit

Status: **CLOSED**, subject to CI on this revision.

## Final inventory method

All runtime Python files outside `app/db.py` were re-inspected for direct SQL patterns after DATA-ACCESS-CONSOLIDATION-001 through 003.

The final audit distinguishes:

1. core business/API/service access to NEXUS application tables, which must route through `app/db.py`;
2. subsystem-owned repositories/storage, which intentionally own their own persistence contract;
3. explicit destructive/maintenance tooling, which is not an application runtime data-access layer.

## Business/API/service SQL

### Migrated in phase 004

`app/services/analytics_service.py` was the only remaining business/service-layer direct SQL consumer discovered.

Its two reads were moved to:

- `db.analytics_closed_signals(start_iso, end_iso)`
- `db.analytics_active_signal_count()`

The helpers preserve the previous current-cycle fallback, CLOSED/date filtering, projection, `closed_at DESC` ordering, and active-count semantics.

### Final business/API status

No direct `db.conn()` / raw SQLite access remains in the audited primary business/API layers:

- `app/miniapp_api.py`
- `app/miniapp_admin_api.py`
- `app/autotrade/api.py`
- `app/services/analytics_service.py`
- `app/services/license_service.py`
- `app/services/pricing_service.py`
- `app/routers/analytics.py`
- `app/routers/subscriptions.py`

Existing signal/trading behavior remains routed through canonical `app/db.py` functions.

## Intentional SQL whitelist

The following direct SQL is intentionally retained outside `app/db.py`.

### `app/analysis_center.py`

Classification: **SUBSYSTEM-OWNED PERSISTENCE**

Owns only `analysis_sessions` and `analysis_updates`, including their subsystem schema and CRUD lifecycle. Those tables are private to Analysis Center and are not shared core signal/payment/AutoTrade tables.

Action: **WHITELIST / KEEP**.

### `app/content/repository.py`

Classification: **DEDICATED REPOSITORY**

Owns `content_posts` and `content_registry` behind the content repository abstraction.

Action: **WHITELIST / KEEP**.

### `app/daily_stickers/storage.py`

Classification: **DEDICATED STORAGE**

Owns `daily_stickers` and `daily_sticker_deliveries`.

Action: **WHITELIST / KEEP**.

### `app/storage/sqlite_storage.py`

Classification: **FRAMEWORK STORAGE BACKEND**

Owns the aiogram FSM `fsm_context` persistence contract and separate storage database behavior.

Action: **WHITELIST / KEEP**.

### `app/signal_agent/context/store.py`

Classification: **SIGNAL AGENT STORE**

Owns Signal Agent context snapshots/source/runtime tables through its explicit Store class and database path.

Action: **WHITELIST / KEEP**.

### `app/signal_agent/ict/store.py`

Classification: **SIGNAL AGENT STORE**

Owns ICT event/link/runtime persistence through its explicit Store class.

Action: **WHITELIST / KEEP**.

### `app/signal_agent/market_data/store.py`

Classification: **SIGNAL AGENT STORE**

Owns quote/candle/runtime persistence through its explicit MarketDataStore abstraction.

Action: **WHITELIST / KEEP**.

### `reset_clean_cycle.py`

Classification: **DESTRUCTIVE MAINTENANCE TOOL**

This is an explicit offline/administrative reset utility. It intentionally opens SQLite directly to checkpoint, back up, execute a single `BEGIN IMMEDIATE` reset transaction, reset AUTOINCREMENT state, and clear the separate FSM database.

It is not imported as an application runtime repository.

Action: **WHITELIST / KEEP**.

## Not classified as SQL

Text occurrences such as UI wording containing the English word "select" are not database statements and were excluded from the inventory.

## Regression gate

`tests/test_data_access_consolidation.py` now verifies:

- analytics projection/current-cycle/active-count equivalence;
- primary business/API/service modules do not open direct `db.conn()` or `sqlite3.connect()` connections;
- the direct-SQL whitelist is explicit in this closure document;
- phase 001–003 idempotency, ordering, projection and atomicity tests remain active.

The test file is already included in NEXUS Mini App CI.

## Closure decision

**DATA ACCESS CONSOLIDATION: CLOSED**

Reason:

- no remaining direct SQL was found in the audited primary business/API/service data-access paths after migrating analytics;
- remaining SQL is subsystem-owned repository/storage or explicit maintenance tooling;
- no schema, signal decision, risk, TP/SL, trailing, execution, broker truth or Telegram lifecycle semantics were changed by closure.

Any future direct SQL introduced into a primary business/API/service module should be treated as a regression unless an explicit architecture decision adds it to this whitelist.
