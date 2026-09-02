# NEXUS v0.6.0 — Runtime-04

## Fixes
1. MT5 CLOSE events now publish the final result through the same Telegram reply-chain as bot-managed/manual close results.
2. MT5 close reason is populated from `DEAL_REASON` (TP, SL, manual/client/mobile/web/expert, stop-out, etc.).
3. CLOSE delivery is retried from the terminal if the position is already closed but the HTTP event delivery fails.
4. Admin Signal Center has a per-signal trailing-profile selector T01–T07. The selected profile is sent as `trailing_code`; backend snapshots the immutable profile into `trailing_config` for that signal.
5. Admin Signal panel gets a dedicated minimize control and a wider/consistent layout so the panel does not lose its minimize action after lifecycle repaint.
6. The existing per-signal trailing state is retained; signal ID is the business identity and MT5 position identifier/ticket remains the runtime execution identity.

## Validation
- Python compileall: PASS
- Full pytest: 182 passed, 3 skipped

## Telegram close reply
For an MT5-driven close, the backend now sends a result reply before marking the signal CLOSED. If one configured channel fails, the other may still receive the result; if all channels fail, the MT5 event remains retryable instead of being silently treated as delivered.

## Trailing contract
Recommended canonical payload:
```json
{
  "trailing_code": "NEXUS_TRAIL_06",
  "trailing_config": {
    "code": "NEXUS_TRAIL_06",
    "version": 1,
    "break_even_r": 0.5,
    "trail_step_r": 0.35,
    "lock_step_r": 0.25
  }
}
```
The backend stores this snapshot with the signal. Telegram caption should be treated as presentation, not as the authoritative control channel. If a human-readable caption is needed, use e.g. `Trailing: NEXUS_TRAIL_06 | BE=0.50R | STEP=0.35R | LOCK=0.25R` while keeping the structured JSON authoritative.
