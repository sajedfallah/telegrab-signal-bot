# NEXUS v0.6.0 — Current Debug Handoff

**Purpose:** This document is the authoritative handoff point for continuing the current NEXUS AutoTrade v0.6.0 investigation with another AI/developer connected to this repository.

## 1. Current snapshot

Current local working snapshot:

`NEXUS_v0.6.0_MT5_SIGNAL_AUTHORITY_MULTI_TP_CHANNEL_ACCESS_FINAL_SOURCE_COMPLETE_COMPILE_FIXED_v3`

Local workspace used for validation:

`C:\Users\Administrator\Desktop\NEXUS_v0.6.0_MT5_SIGNAL_AUTHORITY_MULTI_TP_CHANNEL_ACCESS_FINAL_SOURCE_COMPLETE_COMPILE_FIXED_v3\work060`

Latest source archive supplied in the ChatGPT workspace:

`NEXUS_v0.6.0_MT5_SIGNAL_AUTHORITY_MULTI_TP_CHANNEL_ACCESS_FINAL_SOURCE_COMPLETE_COMPILE_FIXED_v3.zip`

Archive SHA-256:

`14b67fbb1846adf1d0a230022603377694d4f617a2305067559fc0dfc5a90479`

Target runtime version:

`0.6.0`

## 2. Verified status

### Python test suite

The current corrected workspace reached:

`182 passed in 10.51s`

Earlier failures were caused by tests expecting EA version `1.60` while the source had `1.61`. That regression was corrected; the current test suite is green.

### Backend service

Windows command:

`nexus status`

Observed:

- service state: RUNNING
- HTTP: 200
- `{"ok":true,"service":"nexus-autotrade","version":"0.6.0"}`

### MT5

The current `NEXUS_AutoTrade.mq5` source was successfully compiled after fixing the following source problems:

- unbalanced parentheses / unexpected end of program
- missing `PaintStatusPanel`
- missing `SetPanel`
- missing global `g_admin_signal_busy`
- missing global `g_admin_issue_nonce`

Final compile state reported by the user: **0 errors, 0 warnings**.

## 3. Current production-blocking functional bug

The remaining issue is NOT compilation and NOT basic backend availability.

The EA is attached to:

`XAUUSD.ec, M5`

The EA continuously polls the backend and logs messages such as:

`NEXUS SIGNAL POLL: after_id=5 limit=50 force_admin=NO`

This proves the polling loop is alive.

A real signal was successfully received by MT5:

`NEXUS SIGNAL NX-0005 | RECEIVED | requested=XAUUSD.EC | type=MARKET | direction=BUY | entry=4356.00000 | sl=4346.00000`

Symbol mapping also succeeded:

`NEXUS AutoTrade: symbol mapped XAUUSD.EC -> XAUUSD.ec`

The signal was then rejected before order submission:

`NEXUS SIGNAL NX-0005 | REJECTED | reason=entry deviation 0.1767% exceeds 0.0000%`

Therefore the current confirmed execution chain is:

`Backend signal exists -> EA polling works -> signal received -> symbol mapping works -> entry-deviation validation rejects -> OrderSend is not reached.`

## 4. Swagger verification already performed

### GET signals

Endpoint:

`GET /api/v1/admin/mt5/signals`

Without the account header the API returned:

`403 {"detail":"account number is required"}`

With the required MT5 account and admin token headers, the endpoint returned HTTP 200 and exposed the active signal list.

### POST signal

Endpoint:

`POST /api/v1/admin/mt5/signals`

Observed validation sequence:

1. Invalid JSON -> HTTP 422 JSON decode error.
2. `lot_size=0` -> HTTP 422, `Input should be greater than 0`.
3. Correct JSON and positive lot size, plus required admin/account headers -> HTTP 200 and a new signal ID was generated.

A successful signal example was `NX-0005`.

**Important:** secrets/tokens must never be committed to GitHub. The headers above are documented conceptually only; do not copy real token values into source or documentation.

## 5. Entry-deviation issue

The created MARKET signal contained:

`max_entry_deviation_pct = 0`

The EA interpreted this as an allowed deviation of exactly zero percent.

At execution time:

- actual deviation: `0.1767%`
- allowed deviation: `0.0000%`
- result: REJECTED

This behavior must be audited against the intended API/EA contract. Do NOT simply remove the validation.

Determine explicitly whether zero means:

A. zero deviation allowed,
B. no deviation limit, or
C. a default policy should be applied for MARKET orders.

The fix must be deterministic and documented.

For MARKET orders also verify:

- BUY uses current Ask for execution checks.
- SELL uses current Bid.
- `entry_price` is treated correctly as signal/reference price versus executable price.
- spread is handled according to the intended contract.
- deviation is checked at the correct stage.
- stale MARKET entries do not cause silent or unexplained rejection.

## 6. Second critical bug: ISSUE SIGNAL UI has no visible action

The current MT5 SIGNAL panel contains:

- SYMBOL
- ENTRY
- SL
- TP1..TP5
- RISK %
- BUY / SELL
- MARKET / LIMIT
- ISSUE SIGNAL
- FREE / VIP / BOTH
- EXISTING SIGNAL ID
- VALUE
- BE / CLOSE
- CANCEL / SET SL / SET TP / TRAIL

Current observation:

**ISSUE SIGNAL appears to have no action in the current runtime state.**

When the user clicks it, there is no reliable visible indication that:

- the click handler fired,
- the input values were read,
- the POST request was sent,
- the backend responded,
- a signal ID was generated,
- the UI was updated,
- direct execution was started.

This must be debugged from the actual source, not inferred from the UI appearance.

## 7. Required ISSUE SIGNAL trace

Trace the complete path:

`OnChartEvent`

-> `OBJECT_CLICK`

-> button/object name matching

-> ISSUE SIGNAL handler

-> input extraction

-> direction

-> order type

-> symbol

-> entry

-> SL

-> TP1..TP10

-> risk

-> channel/access

-> request JSON

-> HTTP POST

-> HTTP status

-> response body

-> JSON parse

-> canonical `signal_id`

-> UI update

-> direct execution / polling

Every stage must have a correlation ID and explicit logging.

Recommended log format:

`[NX-XXXX] ISSUE START`

`[NX-XXXX] INPUTS ...`

`[NX-XXXX] POST SENT`

`[NX-XXXX] POST RESPONSE status=...`

`[NX-XXXX] SIGNAL CREATED id=...`

`[NX-XXXX] EXECUTION START`

`[NX-XXXX] EXECUTION RESULT ...`

If a stage fails:

`[NX-XXXX] FAILED stage=<stage> reason=<reason>`

No silent failures.

## 8. Polling/cursor audit

Current logs include:

`NEXUS SIGNAL POLL: after_id=4 limit=50 force_admin=NO`

and later:

`NEXUS SIGNAL POLL: after_id=5 limit=50 force_admin=NO`

Audit:

- when `after_id` advances;
- whether it advances before or after execution;
- whether a failed execution can be retried;
- whether a rejected signal is accidentally lost;
- whether `force_admin=YES` is required for Admin-issued signals;
- whether authorization filters remove a signal from the EA's visible result;
- whether the cursor is persisted correctly.

A Signal must not be irreversibly skipped merely because it was received but failed execution.

## 9. Direct execution audit

The intended Admin flow is:

`ISSUE SIGNAL`

-> backend creates canonical signal

-> valid `signal_id`

-> Direct Execution or normal polling

-> execution validation

-> risk sizing

-> OrderSend

-> actual MT5 order/position

-> SL/TP

-> lifecycle receipt

-> Telegram reporting

If Direct Execution exists in the source, determine exactly why it is not visibly triggered after the UI click.

## 10. Order execution audit

Inspect `TradeManager.mqh` and related execution code.

Before `OrderSend`, log:

- signal ID
- broker symbol
- direction
- order type
- requested entry
- current Bid
- current Ask
- volume
- SL
- TP
- deviation
- risk parameters

After `OrderSend`, log:

- retcode
- order ticket
- deal ticket
- position ticket
- broker comment
- `GetLastError()` where applicable

On failure:

`EXECUTION FAILED: stage=... retcode=... error=... reason=...`

Do not return a generic false without diagnostics.

## 11. Risk/volume audit

For:

`risk_percent=1`

and:

`volume_mode=RISK`

verify:

- SL distance
- tick size
- tick value
- contract size
- equity/balance basis
- minimum volume
- maximum volume
- volume step
- normalization
- broker stops level
- freeze level

The backend should not require `lot_size=0` if the contract requires a positive value. If RISK mode is intended to calculate volume, define that contract consistently across API and EA.

## 12. Telegram reporting audit

Telegram must report real lifecycle events only.

Expected lifecycle:

`SIGNAL_ISSUED`

-> `SIGNAL_RECEIVED`

-> `EXECUTION_STARTED`

-> `EXECUTION_ACCEPTED` or `EXECUTION_REJECTED`

-> `ORDER_CREATED`

-> `POSITION_OPENED`

-> `SL_TP_APPLIED`

-> `EXECUTION_RECEIPT`

-> `TELEGRAM_NOTIFICATION`

Do not claim execution success unless MT5 actually created the order/position.

If execution is rejected, reporting must distinguish rejection from successful execution.

## 13. Required source files for audit

MT5:

- `mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5`
- `mt5/NEXUS_AutoTrade/Include/NexusTypes.mqh`
- `mt5/NEXUS_AutoTrade/Include/APIClient.mqh`
- `mt5/NEXUS_AutoTrade/Include/JsonLite.mqh`
- `mt5/NEXUS_AutoTrade/Include/SignalParser.mqh`
- `mt5/NEXUS_AutoTrade/Include/SymbolMapper.mqh`
- `mt5/NEXUS_AutoTrade/Include/TradeManager.mqh`
- `mt5/NEXUS_AutoTrade/Include/RiskManager.mqh`
- `mt5/NEXUS_AutoTrade/Include/TrailingEngine.mqh`
- `mt5/NEXUS_AutoTrade/Include/CommandManager.mqh`

Backend:

- `app/main.py`
- `app/autotrade/api.py`
- `app/autotrade/service.py`
- `app/autotrade/symbol_registry.py`
- `app/config.py`
- relevant database/storage modules
- relevant Telegram reporting code

Tests:

- `tests/test_v060_signal_authority.py`
- `tests/test_v060_mt5_signal_authority_multitp.py`
- `tests/test_v060_channel_access.py`
- `tests/test_v060_compile_source_hardening.py`
- `tests/test_mt5_execution_diagnostics_static.py`
- `tests/test_runtime_hardening_static.py`
- `tests/test_autotrade_ex5_delivery.py`
- `tests/test_mt5_license_input_paste_static.py`
- all related execution/reporting tests

## 14. Existing compile regressions already fixed

Previous compile errors included:

- `unexpected end of program`
- `unbalanced parentheses`
- undeclared `PaintStatusPanel`
- undeclared `SetPanel`
- undeclared `g_admin_signal_busy`
- undeclared `g_admin_issue_nonce`

These must not be reintroduced.

## 15. Acceptance criteria for the next fix

The next implementation is accepted only when all are true:

1. Python tests: `0 failed`.
2. MT5 compile: `0 errors`.
3. MT5 compile: `0 warnings`.
4. ISSUE SIGNAL click produces visible deterministic action/logging.
5. Backend POST succeeds for valid inputs.
6. Signal ID is returned and displayed/logged.
7. EA receives the intended Signal.
8. Authentication/authorization remains enforced.
9. Symbol mapping succeeds.
10. MARKET entry/deviation policy is correct and documented.
11. Risk sizing produces valid broker volume.
12. OrderSend is actually reached for a valid signal.
13. A real MT5 order/position is created.
14. SL and TP are applied correctly.
15. Lifecycle/receipt is generated from real execution.
16. Telegram reporting reflects the real lifecycle.
17. Failed execution is never reported as success.
18. Signal cursor does not lose failed/rejected signals.
19. No secrets are committed.
20. No existing v0.6.0 regression is introduced.

## 16. Important development rule

Do not solve the current issue by:

- deleting validation;
- hardcoding successful execution;
- bypassing authentication;
- bypassing risk controls;
- suppressing errors;
- advancing the cursor before execution is safely handled;
- fabricating receipts;
- fabricating Telegram success;
- changing tests merely to make CI green.

The goal is a real end-to-end fix.

## 17. Immediate next action

Start with the ISSUE SIGNAL click path and the MARKET entry-deviation contract simultaneously.

First prove whether the button generates a POST request.
Then prove the exact API payload and response.
Then prove the signal reaches the EA.
Then prove the deviation decision.
Then prove OrderSend and its retcode.
Then prove lifecycle receipt and Telegram reporting.

Do not jump directly to Telegram debugging until actual MT5 execution is proven.
