# NEXUS v0.5.7 — Final Test-Ready Release

## Included fixes

- Telegram subscription page reduced to exactly three products: `VIP`, `AutoTrade`, `VIP + AutoTrade`.
- Subscription plan buttons render price exactly once using a stable LTR format.
- Added signal timeframe selection and included timeframe in the signal payload/caption.
- Unified mobile-first MARKET/LIMIT signal caption with order type, entry, SL, TP, R:R, timeframe, direction and symbol.
- Limit activation lifecycle made idempotent so manual activation and broker-confirmed activation cannot publish duplicate channel updates.
- MT5 LIMIT execution hardened with broker stop/freeze-level validation, pending-order expiration-mode resolution, normalized prices and detailed broker diagnostics.
- MT5 OPEN event IDs are deterministic, preventing retry-driven duplicate lifecycle publications.
- Status panel enlarged and reorganized into tabs with a unified card, diagnostic checks and a minimize state that also hides manual destination controls.
- MT5 source package contains only the current source and required include files; stale EX5 binaries were removed.
- Market-facing MQL5 `#property version` is `1.57`; runtime EA version remains `0.5.7`.
- Runtime secrets, virtual environments, caches, databases and generated logs are excluded from the release package.

## Verification

- `python -m compileall -q app tests` — passed.
- `python -m pytest -q` — **127 passed, 3 skipped**.
- Actual MetaEditor/MQL5 binary compilation must be performed on Windows/MetaEditor from the included `mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5` source. No stale EX5 is shipped.
