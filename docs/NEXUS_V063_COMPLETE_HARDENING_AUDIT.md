# NEXUS v0.6.3 — Complete Hardening Audit

Date: 2026-09-02

## Canonical source audited

`NEXUS_v0.6.3_TRAILING_EXECUTION_TRUTH_HARDENED`

The supplied source contains the complete `app/`, `mt5/`, and `tests/` trees. The GitHub `main` branch does not yet contain that complete browsable source tree, so this branch records the audit/fix delta and makes the repository sync gap explicit.

## Validation performed

Before the final UI cleanup fix:

- `pytest -q`: **206 passed, 3 skipped**
- Python compile check: **PASS**

After the final UI cleanup fix:

- focused regression: **7 passed**
- full `pytest -q`: **207 passed, 3 skipped**

## Known P0/P1 items re-audited

### MARKET entry deviation

The API request model uses positive-only optional deviation thresholds. Literal zero is rejected rather than being forwarded as an impossible `0.00000%` tolerance. When the field is omitted, the EA uses the configured safe default (`InpDefaultMaxEntryDeviationPct`, currently 0.20%). BUY validation uses Ask and SELL validation uses Bid.

### ISSUE SIGNAL path

The v0.6.3 source contains an explicit `sig_issue` chart-event mapping to `IssueAdminSignal()`. The handler validates inputs, creates the canonical backend signal, checks the canonical response and directly processes the exact signal object returned by the POST so a stale polling cursor cannot hide an Admin-issued signal.

A remaining UI defect was found during this audit: after the click changes the button text to `ISSUING...`, multiple terminal paths only cleared `g_admin_signal_busy` and did not restore the visible button label. The fix centralizes cleanup in `FinishAdminSignalIssue()` and restores both text and button state on every success/failure path after issuing begins.

### Execution truth / trailing

v0.6.3 retains the v0.6.2 live-truth/receipt hardening and adds:

- SL/TP modifications verified by broker retcode and re-read live position state.
- Partial close volume normalized to broker min/step.
- Partial close success only after confirmed live-volume reduction.
- Full close success only after confirmed position disappearance.
- TP1..TP10 state changes only after confirmed execution.
- bounded partial-close retry/backoff.
- no backwards SL movement.
- Trailing 05/07 runner logic only after confirmed target execution.
- no lifecycle/trailing screenshots.

## Repository blocker

`main` currently stores the legacy bootstrap/documentation snapshot, not the complete v0.6.3 browsable source tree. The complete source must be synchronized before GitHub CI can independently compile/test the exact current product source.

## Production gate

Do not label the build Production Ready until Windows/MetaEditor reports `0 errors, 0 warnings` on the exact current EA and a real MT5 demo/broker E2E run proves:

`ISSUE SIGNAL -> canonical POST -> signal_id -> EA processing -> validation -> risk sizing -> OrderSend -> actual position/order -> SL/TP -> reliable receipt -> Telegram lifecycle truth`.

No success status is acceptable without a real MT5 order/position result.
