# AI / Developer Handoff

Use this document when another AI coding agent or developer takes over NEXUS.

## Canonical baseline

**Start from repository v7.0.0 or a later descendant.** Do not reconstruct the project from old ZIP names or earlier chat descriptions.

## Product intent

NEXUS is not only a Telegram signal sender. It is a subscription/licensing business platform whose most sensitive domains are:

- payment integrity
- entitlement/license access
- signal publication state
- signal update/result history
- automated reporting

A change that makes the UI prettier but can duplicate a payment, invalidate access, lose a signal message ID, or publish a result twice is a regression.

## Non-negotiable invariants

1. Never commit `.env`, bot tokens, wallets intended as secrets, real payment credentials, DBs, logs or backups.
2. Admin permissions are based on Telegram user ID in `ADMIN_IDS`.
3. A paid/admin active license should unlock the features its entitlement snapshot grants.
4. VIP access must not be inferred merely from a button click or channel membership.
5. FREE/VIP publication status and message IDs are independent.
6. Live signal updates reply to the **latest message for that signal per channel**.
7. Signal publication and final result are **one framed chart photo + caption**, not an extra result card image.
8. Take-profit count is dynamic.
9. Forex results use pips; Crypto results use percent.
10. Result calculations are direction-aware.
11. Metal pip size is configurable; do not silently impose a broker convention.
12. Public channel reports keep FREE and VIP statistics separate.
13. In Persian mode, user-facing field labels should be Persian; in English mode they should be English. Avoid mixed-language layouts except immutable technical identifiers.
14. Preserve chat cleanliness and navigation.
15. Existing production DBs must migrate in place without losing business records.

## High-risk files/domains

### `app/db.py`

Changes can affect payments, licenses, reports and migrations. Add tests before altering transaction/migration behavior.

### payment handlers in `app/main.py`

Important logic includes resource reservation/refund, receipt lifecycle, admin approval and license activation.

### signal lifecycle in `app/main.py`

Publication, reply chaining and close/result must be tested for FREE-only, VIP-only and BOTH.

### `app/services/license_service.py`

Entitlement rules are business-critical. Paid license snapshots must remain auditable.

### `app/storage/sqlite_storage.py`

Must remain compatible with aiogram 3.x `BaseStorage`. Losing FSM persistence is a user-visible regression.

## Safe development sequence

For a feature:

1. identify affected domain/service
2. add/adjust DB migration if required
3. add pure/service logic
4. add tests
5. wire Telegram router/handler
6. test all access variants
7. update documentation
8. commit without runtime secrets

## Known architectural debt

- `app/main.py` is still large and owns many domains.
- primary SQLite access is still largely synchronous.
- long polling is the current deployment model.
- a durable background task queue is not yet present.
- full web/API separation does not exist yet.

Do not "fix" all of these in one rewrite. Incremental extraction is the intended strategy.

## Current tests

Baseline test suite covers:

- Forex BUY/SELL
- configurable XAU pip size
- Crypto SHORT
- R:R
- SQLite WAL/busy timeout
- FREE/VIP report separation
- paid license history behavior
- client menu order
- final result single-photo behavior
- persistent FSM wiring
- modular router/service/state structure
- plan entitlement/renewal behavior
- license upgrade preservation
- paid license entitlement snapshots
- analytics grouping

## Deferred functionality

Do not claim these are implemented:

- automated Vision/OCR chart extraction
- actual Auto Trade order execution
- MT5 bridge
- full Mini App
- production PostgreSQL

## Preferred next work

Prioritize v7.1 Production & Monitoring before Mini App/Vision/Auto Trade. See `docs/ROADMAP.md`.
