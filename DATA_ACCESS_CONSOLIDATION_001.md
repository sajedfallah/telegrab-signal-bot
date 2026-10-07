# DATA-ACCESS-CONSOLIDATION-001

Baseline branch: `refactor/repository-consolidation`

## Objective

Inventory direct SQL outside `app/db.py`, classify intentional storage/repository boundaries versus business/API-layer dispersion, and migrate only behavior-equivalent duplicate queries to canonical `app.db` functions.

## Inventory

| File | Direct SQL concern | Caller / behavior | Existing canonical DB API | Decision |
| --- | --- | --- | --- | --- |
| `app/miniapp_api.py` | MT5 account lookup | `_autotrade(uid)` Mini App bootstrap/status | `db.mt5_account()` | **MIGRATED** |
| `app/miniapp_api.py` | Exchange account lookup | `_autotrade(uid)` | `db.exchange_account()` | **MIGRATED** |
| `app/miniapp_api.py` | Recent execution history | `_autotrade(uid)` | Similar `db.autotrade_trade_executions()`, but ordering/projection differ | KEEP; not exact-equivalent |
| `app/miniapp_api.py` | Existing pending/approved payment by invoice/user | receipt idempotency | No exact canonical helper found | KEEP |
| `app/miniapp_api.py` | Admin receipt upsert | Telegram receipt delivery | `db.save_admin_receipt()` | **MIGRATED** |
| `app/miniapp_api.py` | Payment delivery status updates | receipt success/failure persistence | No exact behavior-equivalent helper confirmed | KEEP |
| `app/miniapp_admin_api.py` | Latest ADMIN heartbeat/account selection | Admin account resolution/status | `db.mt5_live_accounts()` is broader and changes filtering semantics | KEEP |
| `app/miniapp_admin_api.py` | Live row by account/signal | Live signal card | `db.mt5_live_for_signal()` differs in case/nexus filtering | KEEP |
| `app/miniapp_admin_api.py` | MT5_ADMIN signal list | Admin signals endpoint | `db.list_mt5_admin_signals()` | **MIGRATED** |
| `app/miniapp_admin_api.py` | Managed OPEN/PENDING rows | Admin positions endpoint | Split helpers exist, but current classification semantics are broader | KEEP |
| `app/autotrade/api.py` | Existing execution business-identity lookup | live-state repair/idempotency | Related DB execution helpers exist, but no exact query contract | KEEP |
| `app/services/analytics_service.py` | Closed-signal analytics period query | analytics overview/symbol/trailing/channel reports | No exact canonical helper found | KEEP |
| `app/services/analytics_service.py` | Active signal count for current cycle | analytics overview | No exact canonical helper confirmed | KEEP |
| `app/content/repository.py` | Content tables and queries | dedicated content repository abstraction | Intentional repository boundary | KEEP |
| `app/daily_stickers/storage.py` | Sticker tables and queries | dedicated storage abstraction | Intentional storage boundary | KEEP |
| `app/storage/sqlite_storage.py` | FSM table and state queries | aiogram storage backend | Intentional storage boundary | KEEP |
| `app/analysis_center.py` | Analysis session/update tables | analysis subsystem-local persistence | Intentional subsystem storage; no duplicate app.db API confirmed | KEEP |

## Tests / callers mapped

- Mini App API routing/auth: `tests/test_miniapp_api.py`
- Admin Mini App route contract: `tests/test_admin_miniapp_connectivity.py`
- MT5 live-state/idempotency: `tests/test_v062_live_truth.py`
- AutoTrade payload/account behavior: `tests/test_autotrade_backend.py`, `tests/test_autotrade_api_compat.py`
- MT5 history/reconciliation: `tests/test_mt5_history_reconciliation.py`
- Analytics/report behavior: `tests/test_reports_and_access.py`
- New focused data-access regression: `tests/test_data_access_consolidation.py`

## Implemented consolidation

The following direct SQL was removed from API/business callers without changing schema or domain behavior:

1. Mini App MT5 account lookup -> `db.mt5_account(uid)`
2. Mini App exchange account lookup -> `db.exchange_account(uid)`
3. Mini App admin-receipt upsert -> `db.save_admin_receipt(...)`
4. Admin Mini App MT5_ADMIN signal list -> `db.list_mt5_admin_signals(100)`

No SQL was moved when filters, ordering, row projection, case handling, lifecycle semantics, or idempotency rules differed from an existing `app.db` function.

## Non-goals

- No schema migration.
- No status-enum normalization.
- No signal/risk/TP/SL/trailing changes.
- No MT5 execution behavior changes.
- No broad repository/storage rewrite.


# DATA-ACCESS-CONSOLIDATION-002

## Scope

Priority SQL remaining after phase 001:

1. Payment receipt idempotency.
2. Mini App execution history.
3. Admin MT5 account/live-state queries.

## Canonical helpers added

| Caller behavior | New canonical helper | Equivalence contract |
| --- | --- | --- |
| Find duplicate payment for same user/invoice | `db.find_invoice_payment(telegram_id, invoice_id)` | Same statuses: pending/approved; same newest-id ordering; same two-column projection |
| Mini App recent execution history | `db.miniapp_execution_history(telegram_id, limit=20)` | Same selected columns; same `ORDER BY id DESC`; same default limit 20 |
| Admin MT5 account selection | `db.latest_admin_mt5_account(configured_accounts)` | Same ADMIN-only filtering, latest heartbeat preference, configured-first fallback |
| Admin heartbeat status row | `db.admin_mt5_heartbeat(account_number)` | Same three-column projection and ADMIN/account filtering |
| Admin live signal row | `db.mt5_latest_managed_signal_state(account_number, signal_code)` | Same case-insensitive signal-code match, managed-only filter, OPEN/PENDING filter, newest heartbeat |
| Admin active live rows | `db.mt5_managed_active_state(account_number)` | Same managed-only OPEN/PENDING filter and `last_seen_at DESC` ordering |

## Regression evidence

`tests/test_data_access_consolidation.py` now verifies:

- payment idempotency ignores failed rows and returns the newest pending/approved row for the same user+invoice;
- execution-history projection, ordering and limit are unchanged;
- Admin account selection preserves configured fallback and latest-seen behavior;
- Admin heartbeat lookup preserves role/account filtering;
- live signal lookup remains case-insensitive and managed-only;
- active Admin live-state rows preserve POSITION/ORDER data used by caller-side classification;
- migrated API callers no longer contain the priority SQL strings.

The existing Mini App CI already runs this test file, so the new phase-002 cases are release-gated.

## Deferred SQL

The following remain outside `app/db.py` because this phase did not establish exact equivalence with an existing/new bounded helper:

- Mini App payment delivery success/failure UPDATE statements;
- AutoTrade live-state repair execution identity lookup;
- analytics/report queries;
- intentional subsystem repositories/storage modules.

No schema or lifecycle semantics changed.
