# SIGNAL-AGENT — Release A: Market Data Foundation

Shadow/data-only foundation. It does not detect ICT setups, issue signals, publish Telegram messages, or alter the existing MT5 Signal Authority.

## Configuration
- SIGNAL_AGENT_MARKET_DATA_ENABLED=0 (safe default)
- SIGNAL_AGENT_SYMBOLS=XAUUSD
- SIGNAL_AGENT_MARKET_DATA_PROVIDER=MT5
- SIGNAL_AGENT_STALE_AFTER_SECONDS=30
- SIGNAL_AGENT_POLL_INTERVAL_SECONDS=5

## Runtime
MarketDataRuntime hydrates the latest persisted quote and D1/H4/H1/M15/M5 candle state on construction. When explicitly enabled, start() launches an always-on daemon worker; stop() provides clean shutdown. Disabled is the safe default.

## Data contract
Quotes persist bid/ask/spread/timestamp. Candles persist D1/H4/H1/M15/M5 OHLCV with UTC open times. Empty candle responses and stale quotes are errors. Runtime health persists per-symbol OK/ERROR state.

## Timeframes
The MT5 adapter requests native M5/M15/H1/H4/D1 bars. UTC bucket helpers are deterministic and covered at M5/M15/H1/H4/D1 boundaries for derived/verification use.

## Safety boundary
This package has no Telegram publication or signal-authority imports. Release A is shadow-only.
