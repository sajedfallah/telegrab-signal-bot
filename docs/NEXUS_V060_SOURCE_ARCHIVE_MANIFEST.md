# NEXUS v0.6.0 Source Archive Manifest

## Canonical local snapshot

Filename:

`NEXUS_v0.6.0_MT5_SIGNAL_AUTHORITY_MULTI_TP_CHANNEL_ACCESS_FINAL_SOURCE_COMPLETE_COMPILE_FIXED_v3.zip`

SHA-256:

`14b67fbb1846adf1d0a230022603377694d4f617a2305067559fc0dfc5a90479`

Local workspace:

`C:\Users\Administrator\Desktop\NEXUS_v0.6.0_MT5_SIGNAL_AUTHORITY_MULTI_TP_CHANNEL_ACCESS_FINAL_SOURCE_COMPLETE_COMPILE_FIXED_v3\work060`

## Validation at handoff

- Python: `182 passed in 10.51s`
- MT5 EA: `0 errors, 0 warnings`
- Backend: HTTP 200, service version `0.6.0`

## Archive contents verified locally

The archive contains the complete `work060` source tree, including:

- `app/` FastAPI/autotrade/backend modules
- `mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5`
- `mt5/NEXUS_AutoTrade/Include/*.mqh`
- `tests/` regression suite
- Windows startup/deployment scripts
- requirements and project documentation

## Important

The binary ZIP is the local canonical source snapshot for this handoff. Runtime secrets, `.env`, databases, logs, caches, and customer `.ex5` binaries are intentionally excluded from repository commits.

See `docs/NEXUS_V060_CURRENT_DEBUG_HANDOFF.md` for the authoritative bug state and continuation instructions.
