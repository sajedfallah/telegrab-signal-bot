# NEXUS v0.5.8 — Final Source Test Ready

## AutoTrade / Order Engine
- Supports MARKET, BUY LIMIT, SELL LIMIT, BUY STOP and SELL STOP.
- Manual MT5 pending orders publish lifecycle signals.
- Pending cancellation and expiration are propagated to Telegram.
- Duplicate lifecycle events are protected by durable event IDs.
- Broker stop/freeze-level validation remains enabled for pending orders.
- Telegram-created pending orders can be tracked through MT5 deletion/expiration events.

## License
- AutoTrade payment approval requests the MT5 account before the AutoTrade key is delivered.
- License issuance binds the key to the customer's MT5 account.
- Customer account-change requests require administrator approval and are audited.
- Old account access is disabled after an approved rebind.

## UI
- Signal order menu includes all five order types.
- Pending cards use a unified mobile-friendly structure.
- AutoTrade license page hides an unissued key.

## Validation
- Python compileall: PASS
- Pytest: 133 passed, 3 skipped
- MT5 source package is source-only; compile with MetaEditor before live/demo execution.
