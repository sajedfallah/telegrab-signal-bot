# V3.2 recovery and V3.3 lifecycle foundation

Status: user-supplied VPS output verifies the six baseline V3.2 pytest tests
(6 passed in 2.29s). The tested SHA was not included. Recovery/V3.3 code still
requires external verification; watcher integration remains BLOCKED. No
phase-wide V3.3 PASS is claimed.

## Scope and ownership

`setup_lifecycle_v33.LifecycleStore` is the intended authoritative owner of new
setup state once detector adapters and integration tests pass. It is currently
opt-in and unreferenced by runtime entry points. It does not send Telegram
messages, import MT5 or order modules, start services, or grant authorization.

`lifecycle_evidence_v33` supplies frozen Candle, Sweep, MSS, Displacement, FVG and
Retest contracts. Candle identities include source, symbol, timeframe, explicit
UTC open/close times and OHLC values. Numeric prices are normalized before
hashing. Typed evidence is copied to canonical JSON in SQLite, so caller-side
objects cannot mutate persisted history.

The engine rejects OHLC revisions of the same source candle across events.
`monitor` records terminal closed-price invalidation with exact candle evidence,
or expiration using the supplied decision clock; normal monitoring cannot promote
state. Reopening verifies the append-only triggers and migration ledger.

`lifecycle_snapshot_v33.evidence_frame` copies immutable closed candles from a
single MarketSnapshot and explicit shared context reference for M1/M5. It requires
source-provided closed_at metadata; the existing MT5 adapter lacks this field and
therefore fails this boundary until a separately verified metadata migration.
The trailing live candle is excluded from completed evidence. Missing timeframes,
quotes, stale data, overlapping/future bars or missing metadata fail closed.

The engine verifies geometry and availability of supplied evidence. It does not
discover or prove genuine swing windows, POI qualification, HTF alignment or
broker provenance by itself. Those detector adapters remain integration blockers.
Synthetic fixtures are used only in isolated unit tests.

## V3.2 stabilization

The existing analysis interface is preserved. Changes deep-copy nested tracker
evidence, retain the original stored POI binding, invalidate existing identities
when the POI disappears, serialize read-modify-write transactions, close SQLite
handles, and use snapshot time rather than wall-clock time. The tracker now
rejects missing, duplicate, future and unclosed penultimate candle timestamps and
invalid OHLC; H1 interpretation conservatively excludes its trailing candle.

These modules are used by analysis, not the current watcher publication path.
`fast_scalp.py`, `full_ict_gate.py`, `signal_engine.py` and `signal_watcher.py` have
not been edited. Missing legacy event history, expiry and migrations are handled
by the new isolated store, not retroactively invented for V3.2 records.

## Persistence and recovery

Supply a new isolated SQLite path explicitly. An existing unversioned database,
future schema or a path under NEXUS_DEPLOY is rejected. Version 0 (empty) migrates
transactionally to version 1 with a migration ledger. Existing V3.2 databases are
never adopted or overwritten. All setup specifications, events and publication
reservations are append-only, with SQL triggers preventing UPDATE and DELETE.

Setup identity hashes the complete immutable specification, including its original
POI ID/origin/bounds, direction, strategy, trigger timeframe, HTF context, expiry
and policy. A policy or POI change is a new identity, never an update to the old
one. Scanner adapters must choose a stable discovery timestamp and retain this
identity; repeated detection with changing creation time is not an adapter yet.

The state is recovered from the last append-only event. Event keys are unique per
setup; identical retries return the original event ID, while conflicting key reuse
is rejected. BEGIN IMMEDIATE protects concurrent validations and appends. Recovery
does not infer missing historical events. All stage transitions require the exact
next mandatory state; INVALIDATED, EXPIRED, CANCELLED and SIGNAL_PUBLISHED are
terminal. `expire_due(at=..., snapshot_ref=...)` uses the supplied decision clock
and can run while the feed is stale. A deadline also blocks advancement even if
an expiry sweep has not run yet.

## Chronology decisions and engine disagreements

| Topic | Existing disagreement | V3.3 decision / migration gate |
|---|---|---|
| H1 bias | Fast Scalp midpoint/momentum differs from ICT pivot/fallback | Keep detectors unchanged; shared MTF policy and equivalence fixtures required before replacement |
| Candle close | Fast Scalp uses last bar; tracker/gate drop last trigger bar | New evidence must carry explicit closed_at <= decision time; V3.1 tracker additionally validates UTC intervals |
| Sweep | Each engine rescans independently | Exact reference liquidity candle and reclaim candle; sweep must overlap original POI |
| MSS | Rolling reference windows differ; gate may select another setup | Exact preceding swing and its confirmation candle, same-setup sweep event ID, later close across swing |
| Displacement | Fast Scalp labels MSS displacement without tracker body filter | Distinct measured body vs at least three unique prior baseline candles; directional body required; same-candle MSS exception opt-in and tested |
| FVG | Tracker allows third bar at MSS; gate starts first bar at MSS | Three consecutive closed candles; first cannot precede displacement candle, which cannot precede MSS; stricter than legacy tracker |
| Retest | Current quote touch versus later closed candle | Exact FVG event reference and a strictly later candle overlapping its actual bounds |
| POI | Scanner returns PROVISIONAL, while gate accepts non-TOO_WIDE | Observation allowed, but provisional specification cannot reach ENTRY_READY; qualification must come from a future tested POI adapter |
| Publication | Gate rescans independently, fingerprints exist only in memory | No integration yet; candidate, snapshot and context must match the persisted identity; durable reservation and independent hard gates |

No conflicting detector was removed. Equivalence is NOT established by the
synthetic contract tests. All six existing engines remain to be connected through
tested adapters. In particular, swing_confirmation is an upstream assertion of
confirmation availability; the lifecycle checks its chronology, not pivot quality.

## Publication boundary

ENTRY_READY does not authorize publication. `reserve_publication` requires an
explicit True verdict for all nine named independent gates, the matching setup,
context and entry snapshot, an unexpired setup and a decision within 30 seconds
of the ENTRY_READY snapshot. This is a conservative research default, not a
calibrated strategy threshold. A fingerprint or setup can be reserved only once,
including across restart and concurrent callers. Reservations are deliberately
never automatically released after a crash: uncertain delivery stays blocked.

Only an externally obtained SHADOW receipt can append SIGNAL_PUBLISHED. Receipt
retries are idempotent. This API has no transport and does not evaluate the gates
on behalf of callers. It cannot guarantee exactly-once delivery to Telegram.

No watcher integration is permitted until external V3.2 pytest, detector adapter
equivalence, candidate/verification identity binding, stale feed handling,
independent risk-gate preservation and M1/M5 integration tests pass. No runtime
configuration has been enabled in this change.

## Verification and external action

Local environment: bundled Python has pydantic but no pytest. No package download
was attempted during recovery. Existing six test functions were executed verbatim
via a unittest adapter (tmp_path replaced by TemporaryDirectory), plus four V3.2
regressions. That is actual assertion evidence, but is not pytest collection or
validation on C:\NEXUS_AGENT_TEST, which is absent on this host. Subsequent
user-supplied evidence confirms six baseline pytest tests passed on that VPS;
see nexus_v32_vps_evidence.md. Untracked data/ was present and must be preserved.
The verification script now permits only that known untracked directory and
rejects incoming changes under data/ before updating the checkout.

Latest local V3.3 run: 32 lifecycle tests plus 6 snapshot-boundary tests passed,
including identical-input replay and full LONG/SHORT sequences on M1/M5.

Run on the authorized Windows test host:

```powershell
Set-Location C:\NEXUS_AGENT_TEST
git status --short
git pull --ff-only origin feature/nexus-agent-system-v1
python -m pytest tests/test_agent_setup_tracker_v31.py tests/test_agent_setup_lifecycle_v32.py -q
```

The audit push passed branch, ancestry and clean-worktree checks, but failed
because shell Git has no GitHub credentials. The existing documentation commit
d95085d0c41b9409332c93b01cead549b751603f is preserved as an ancestor, not recreated.
An incremental Git bundle is supplied for transferring that exact commit and this
implementation to the authorized test clone. See the accompanying guarded
PowerShell script; it merges only fast-forward and runs focused tests, without
publishing or deploying. Paste its complete test output before proceeding with
watcher integration.
