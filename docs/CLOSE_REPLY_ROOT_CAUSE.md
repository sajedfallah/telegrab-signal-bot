# NEXUS v0.6.5 — Closed-position Telegram reply investigation

## Confirmed root cause

The broker history-reconciliation path can mark a signal `CLOSED` without creating a Telegram lifecycle reply. If the event-driven `CLOSE` is processed afterwards, the current handler sees the already-closed row and returns before attempting the channel reply.

This creates an order-dependent race:

`broker CLOSE -> history reconcile -> signal CLOSED -> queued/event CLOSE -> early return -> no Telegram result reply`

Remediation is being implemented on `fix/v065-close-reply-hardening`: broker truth may be known first, but a close without a delivered Telegram result is kept in a retryable terminal state and routed through the durable MT5 trade-event queue before final `CLOSED` state.

## Additional risks confirmed in current main

- `BOTH` currently treats one successful channel reply as sufficient to finalize the signal, so a failure in the other channel is not guaranteed to retry.
- Missing-anchor recovery is triggered only when both FREE and VIP anchors are absent; a single missing destination anchor can still fail independently.
- Runtime Telegram credentials/channel permissions cannot be verified from repository contents because `.env` and runtime logs are intentionally not committed. Use the repository diagnostic utility from the hardening branch against the deployed environment.
