# NEXUS AutoTrade — MT5 Compile Requirement

The source of record in this release is **NEXUS AutoTrade v0.5.7** (`NEXUS_EA_VERSION=0.5.7`). The Market-facing `#property version` is `1.57` so MetaEditor does not emit the Market-version warning.

The compiled EX5 binary is intentionally not included in the source package. This prevents an old binary from being shipped against the current MQ5 source.

## Build

1. Open `mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5` in MetaEditor.
2. Keep the `Include` folder beside the MQ5 source.
3. Compile with the current MetaTrader 5 terminal/build.
4. Confirm **0 errors** in the MetaEditor compile output.
5. The generated `NEXUS_AutoTrade.ex5` is the only binary that should be distributed for this source revision.
6. Before customer deployment, set `InpApiBaseUrl` to the production HTTPS API endpoint and compile again.

## Limit-order diagnostics

The current source validates Buy Limit/Sell Limit geometry against broker Bid/Ask plus `SYMBOL_TRADE_STOPS_LEVEL` / `SYMBOL_TRADE_FREEZE_LEVEL`, resolves a broker-supported pending-order expiration mode, logs the exact entry/SL/TP and retcode, and keeps OPEN event IDs deterministic so retries cannot publish duplicate activation messages.
