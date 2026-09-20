# SIGNAL-AGENT — Release A: Market Data Foundation

Shadow/data-only foundation. It does not detect ICT setups, issue signals, publish Telegram messages, or alter the existing MT5 Signal Authority.

## Configuration
- SIGNAL_AGENT_MARKET_DATA_ENABLED=0 (safe default)
- SIGNAL_AGENT_SYMBOLS=XAUUSD
- SIGNAL_AGENT_MARKET_DATA_PROVIDER=MT5
- SIGNAL_AGENT_STALE_AFTER_SECONDS=30

## Data contract
Quotes persist bid/ask/spread/timestamp. Candles persist D1/H4/H1/M15/M5 OHLCV with UTC open times. Runtime health persists per-symbol OK/ERROR state and stale/missing-data errors.

## Recovery
SQLite tables use stable primary keys; a new runtime instance reopens the same database and resumes from persisted candle/quote state. Provider polling is idempotent.

## Safety boundary
This package has no Telegram publication or signal-authority imports. Release A is shadow-only.
