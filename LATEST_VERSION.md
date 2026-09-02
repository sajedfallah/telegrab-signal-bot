# NEXUS — Latest Version

**Current latest audited development snapshot: NEXUS v0.6.3**  
**Scope: Trailing Execution Truth / Reliable Receipts / MT5 Admin Signal Hardening**

Validated against the latest v0.6.3 source snapshot supplied on 2026-09-02.

## Current verified state

- Python unit/static suite before final UI fix: **206 passed, 3 skipped**
- Python unit/static suite after final `ISSUE SIGNAL` UI cleanup fix: **207 passed, 3 skipped**
- Python `compileall`: **PASS**
- MARKET deviation contract hardened: literal zero thresholds are rejected at the API boundary; omitted values fall back to the configured safe default.
- `ISSUE SIGNAL` path includes explicit validation/logging, canonical POST response parsing and direct processing of the returned canonical signal object.
- `ISSUE SIGNAL` button cleanup is centralized so success/error paths cannot leave the UI stuck on `ISSUING...`.
- Reliable execution receipts and live MT5 truth synchronization from v0.6.2 are retained.
- Trailing profiles 01–07 are retained and hardened for execution truth.
- Partial Close success requires broker retcode plus confirmed live-volume reduction.
- Full Close success requires the real position to disappear.
- SL/TP modification success requires broker retcode plus live position confirmation.
- TP state is advanced only after confirmed execution.
- Lifecycle/trailing updates remain text-only replies; no lifecycle screenshot was added.

## Repository source-sync status

The default `main` branch still contains the older bootstrap/documentation layout and does **not** yet contain the complete browsable `app/`, `mt5/`, and `tests/` tree from the v0.6.3 canonical source snapshot. The `fix/v063-complete-hardening` branch records the v0.6.3 audit, regression patch and tests so the source-sync gap is explicit and traceable.

## Production gate

This snapshot is **not declared Production Ready** until both are completed on the real Windows/MT5 environment:

1. MetaEditor compilation: `0 errors, 0 warnings`.
2. Real broker/demo E2E proof: Issue -> canonical signal -> EA receive -> risk sizing -> OrderSend -> actual position/order -> SL/TP -> lifecycle receipts -> Telegram truth reporting.

## Security

Never commit `.env`, Telegram/admin tokens, runtime databases, logs, backups, caches, account secrets, or customer `.ex5` binaries.
