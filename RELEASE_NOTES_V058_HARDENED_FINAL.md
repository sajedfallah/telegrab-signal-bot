# NEXUS v0.5.8 Hardened Final Source

## Verified
- Python compileall: PASS
- Pytest: 143 passed, 3 skipped
- MT5 package is source-only
- EA source version: 1.58 / release 0.5.8

## Key fixes
- VIP-only signals are eligible for AutoTrade polling when the VIP publication exists.
- License supersede + replacement is one SQLite transaction.
- MT5 activate/check/history-reconcile convert AutoTradeError to HTTP 403.
- Admin token checks use constant-time comparison.
- Canonical catalog repair: VIP12M=239 USDT; AEX1M/3M/6M/12M=5/14/27/49 USDT.
- MT5 account-change history is append-only while the current-account row remains one-per-customer.
- Manual MT5 captions use the unified caption engine; literal backslash-n formatting was removed from the manual path.
- Signal timeframe is carried into MT5 trailing state.
- EA local license/config CSV no longer uses FILE_COMMON.
- JSON key lookup is root-object scoped to avoid nested duplicate-key collisions.
- BUY/SELL LIMIT, BUY/SELL STOP and STOP-LIMIT order types are represented in the source model; broker compilation must be performed in MetaEditor.

## Important release condition
The MQL5 compiler is not available in this build environment. Compile `mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5` in MetaEditor on the target machine before generating the EX5. The EX5 must be generated from this exact source package.
