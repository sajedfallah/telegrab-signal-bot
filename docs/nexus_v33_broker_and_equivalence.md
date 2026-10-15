# V3.3 broker validation and detector comparison

The branch was fetched during this execution. Remote HEAD was
d973a0a91bc8199cc8ab38b8d165173b657f47e5 and did not contain e98b4d9.
The local worktree was clean and remote HEAD was an ancestor of local HEAD.
A normal, non-force push was attempted and failed: shell Git could not read a
GitHub username with terminal prompts disabled. No remote availability is claimed.

## Broker clock boundary

`broker_clock_v33` is isolated from the runtime MT5 adapter and all publication
paths. It reads only an explicitly supplied existing export using SQLite mode=ro
and query_only. It never calls schema initialization, defaults to the app DB or
creates a missing source database. Known production directories are rejected.

`BrokerClock` requires a source, an external calibration reference, an explicit
offset from broker wall-clock seconds to UTC, and a validity interval. Zero offset
is explicit, not assumed. Every candle and decision must lie within the attested
clock interval; an interval spanning a broker offset change requires separate
calibrations. The validator does not discover or certify broker clock offsets.

Only real, contiguous successor bars with sufficient UTC capture evidence can
establish a completed intraday candle. Future, millisecond, duplicate, overlapping,
unordered, stale or timezone-naive timestamps fail closed. Missing successor bars
and session/weekend gaps fail closed rather than silently resample or assert a
close. The final bar is never completed evidence. OHLC values are preserved.
Daily sessions remain unsupported until a formal broker session policy exists.

The existing feed sends MqlRates.bar.time and tick.time_msc. It does not carry
calibration references, so the production feed must not be assumed compatible.
All tests use temporary exports and synthetic fixtures. A real read-only broker
export plus independently checked calibration is still required for acceptance.

## Detector-equivalence results

The characterization tests invoke real Fast Scalp, Setup Tracker and Full ICT Gate
functions, with no mocked detector, POI scanner or H1 bias.

| Case | Actual observed result | Integration decision |
|---|---|---|
| Stale feed | All three reject readiness | Agreement on this negative fixture only |
| LONG/SHORT complete fixture | All report readiness, but Fast Scalp and Tracker select different FVG bounds | BLOCK: candidate/gate identity cannot be inferred from matching status |
| Pre-MSS-only gaps | Fast Scalp ENTRY_READY and tracker RETEST_OBSERVED, full gate rejects | BLOCK: incompatible chronology |
| Forming last-bar MSS | Fast Scalp sequence identifies MSS; tracker leaves it unconfirmed | BLOCK: incompatible candle-close semantics |

A passing characterization test confirms the recorded behavior, including the
disagreements. It does not establish detector equivalence or permit deployment.
Legacy runtime algorithms are deliberately unchanged. Reconciliation requires a
shared detector returning exact event IDs, strict evidence equivalence tests and
an explicit strategy migration; silently tightening one publication path would
violate the requirement to preserve existing SHADOW behavior during this stage.

## Persistence validation

Subprocess tests reopen active and terminal setups in fresh Python processes.
They deliberately terminate a child after committing a publication reservation,
before delivery, to prove persistent duplicate suppression. A separate test kills
a child with an uncommitted lifecycle append and verifies SQLite rollback. A
concurrent event test confirms a single history append for identical retries.
No production processes are terminated; only test-owned child interpreters exit.

No new event schema or legacy-data migration is needed in this increment. The
existing versioned, append-only V3.3 store remains the only owner of its state.

## Full regression commands

On a checkout containing this commit:

```powershell
Set-Location C:\NEXUS_AGENT_TEST
git rev-parse HEAD
python -m pytest tests/test_agent_setup_tracker_v31.py tests/test_agent_setup_lifecycle_v32.py tests/test_full_ict_gate_v3.py -q
if ($LASTEXITCODE -ne 0) { throw 'Baseline tests failed' }
python -m unittest discover -s tests -p test_agent_v32_recovery_unittest.py -v
if ($LASTEXITCODE -ne 0) { throw 'V3.2 regression failed' }
python -m unittest discover -s tests -p 'test_agent_*v33*unittest.py' -v
if ($LASTEXITCODE -ne 0) { throw 'V3.3 regression failed' }
```

`tools/run_nexus_v33_regressions.ps1` executes these checks. The guarded bundle
verification script delegates to it. Preserve the VPS untracked data/ directory.
Successful suite execution is necessary but not sufficient for integration:
detector equivalence and actual broker-source acceptance remain BLOCKED.
