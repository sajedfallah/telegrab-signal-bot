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
