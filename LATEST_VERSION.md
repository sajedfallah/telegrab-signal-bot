# NEXUS — Latest Version

**Current latest tested development snapshot: NEXUS v0.6.0**  
**Current debug handoff: v0.6.0 MT5 Signal Authority / Multi-TP / Channel Access**

The current local snapshot has passed the Python regression suite and MT5 compilation, but it is **not yet functionally release-complete**. The remaining blocker is the Admin `ISSUE SIGNAL` path and end-to-end MARKET execution/reporting.

## Current verified state — 2026-09-01

- Backend service: RUNNING, HTTP 200, API version 0.6.0
- Python regression suite: **182 passed in 10.51s**
- MT5 EA compile: **0 errors, 0 warnings**
- EA polling: confirmed active
- Admin signal retrieval through Swagger: confirmed HTTP 200 with required account/token headers
- Admin signal creation through Swagger: confirmed HTTP 200 after valid JSON and positive `lot_size`
- Symbol mapping: `XAUUSD.EC -> XAUUSD.ec` confirmed
- Signal reception in MT5: confirmed for `NX-0005`
- Existing Signal execution rejection: confirmed because `max_entry_deviation_pct=0` produced `0.1767% > 0.0000%`

## Open P0/P1 issues

### P0 — Admin ISSUE SIGNAL button has no observable action

The MT5 SIGNAL panel's `ISSUE SIGNAL` click currently does not provide a reliable visible trace of click dispatch, request creation, backend POST, response parsing, signal ID creation, or direct execution. Audit the full `OnChartEvent -> OBJECT_CLICK -> ISSUE handler -> input extraction -> JSON -> HTTP POST -> response -> signal_id -> execution` chain.

### P0 — MARKET entry-deviation contract

A real signal was received and mapped successfully but rejected before `OrderSend`:

`NEXUS SIGNAL NX-0005 | REJECTED | reason=entry deviation 0.1767% exceeds 0.0000%`

Audit the intended semantics of `max_entry_deviation_pct`. Do not simply remove validation. Define whether zero means zero tolerance, unlimited/no limit, or a default policy. Verify BUY/SELL executable price semantics (Ask/Bid), spread treatment, and stale reference entry handling.

### P1 — End-to-end execution/Telegram proof still pending

The next test must prove: Issue -> signal ID -> EA receive -> validation -> risk sizing -> OrderSend -> actual MT5 position -> SL/TP -> lifecycle receipt -> Telegram reporting. No success may be reported unless the real MT5 event occurred.

### P1 — Cursor/retry safety

Audit `after_id` advancement. A received-but-failed signal must not be silently lost before execution is safely handled.

## Canonical handoff

Read:

`docs/NEXUS_V060_CURRENT_DEBUG_HANDOFF.md`

It contains the full observed logs, source areas, exact debugging sequence, required tests, and acceptance criteria.

## Current source archive

`NEXUS_v0.6.0_MT5_SIGNAL_AUTHORITY_MULTI_TP_CHANNEL_ACCESS_FINAL_SOURCE_COMPLETE_COMPILE_FIXED_v3.zip`

SHA-256:

`14b67fbb1846adf1d0a230022603377694d4f617a2305067559fc0dfc5a90479`

## Security

Never commit `.env`, Telegram tokens, admin tokens, runtime databases, logs, backups, caches, or customer `.ex5` binaries.
