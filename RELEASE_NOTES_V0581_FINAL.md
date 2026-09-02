# NEXUS v0.5.8 P0 — Pending Execution & Lifecycle Hardening

## Implemented
- Telegram → MT5 pending execution now uses a stable MqlTradeRequest + OrderSend path.
- BUY_LIMIT, SELL_LIMIT, BUY_STOP, SELL_STOP, BUY_STOP_LIMIT and SELL_STOP_LIMIT are preserved end-to-end.
- Pending risk sizing uses the requested Entry price.
- EA receipt/status reports pending orders as pending.
- Stop-Limit price is transported and validated.
- Signal creation no longer asks for leverage; Forex and Crypto use Risk % or Fixed Lot.
- Market selection is reporting-only.
- Manual symbols are normalized and a broker-neutral symbol registry is provided, with EPLANET as the default mapping.
- Channel signal cards use one canonical LTR English format.
- Manual lifecycle messages no longer contain literal backslash+n sequences.
- Activation reports requested/executed price and slippage.
- Close reports P/L, performance unit, duration and close reason.
- Persisted lifecycle fields include opened_at, holding_seconds, result_pips and close_reason.
- XAUUSD pip reporting is standardized to 0.1.
- Existing VIP polling, license atomicity, account binding, terminal-local configuration and timeframe-aware trailing hardening are retained.

## Verification
- Python compileall: PASS
- Python test suite: PASS
- MQL5: final compile must be performed in the target MetaEditor.
