# Shared-evidence consumer adapters (research only)

## Boundary and ownership

`research_consumers_v33` introduces separate opt-in adapters. It does not edit or
replace the running Fast Scalp, Setup Tracker, Full ICT Gate or Signal Watcher.
It is a migration boundary for verifying exact evidence identity before moving
any runtime caller. Legacy disagreement tests remain valid and still block a
claim that the current runtime algorithms are equivalent.

`analyze_research` calls the shared detector once. Its frozen ResearchAnalysis
contains the Setup, EvidenceFrame, DetectorPolicy, selected sweep timestamp,
SequenceResult and a canonical integrity fingerprint over those objects.
All adapters consume this analysis without invoking another detector or inferring
H1 bias/POIs independently. Integrity is a consistency check, not a signed proof
of broker provenance or a security authorization token.

## Consumers

- `fast_scalp_research`: M1 only. Exposes original POI, actual sweep price and FVG
  bounds. Completed structural retest is explicit; the state deliberately never
  becomes ENTRY_READY. `publication_allowed` remains False.
- `tracker_research`: M1/M5. Exposes exact event IDs, source candle IDs (including
  referenced liquidity, swing confirmation and displacement baseline), event
  confirmation timestamps and actual FVG bounds. No signal permission is granted.
- `research_candidate`: evidence-only immutable candidate after a closed retest.
  It contains no invented entry, stop or targets. Those require independent
  strategy geometry and risk gates before any future signal integration.
- `full_ict_research`: compares the candidate to the same setup, sequence,
  snapshot, context, decision time, event IDs, direction, profile, POI/FVG geometry
  and source candles. A provisional POI or incomplete/terminal sequence fails.
  `structure_allowed` describes only the research comparison. `allowed` is False
  even when all structural checks pass.
- `persisted_full_ict_research`: additionally reads the explicitly supplied
  isolated lifecycle store, checks its current state and exact matching stored
  event prefix, translates detector references to real stored event IDs, and
  rejects missing, invalidated or expired state. It does not mutate the database.

EvidenceBinding includes snapshot and decision time as well as stable structural
event IDs. A new snapshot can preserve the same structural event IDs but requires
a newly bound candidate. An old candidate cannot be silently verified against a
new snapshot. Changing geometry or source candles while retaining the same
binding also fails. Different POIs with identical numeric bounds are still
different setups.

The persistent read is not a lock across later publication. Any future delivery
path must still perform its independent, atomic lifecycle/reservation recheck.
These adapters never reserve or send a publication and import no order/transport
module. No real-feed acceptance or full entry-risk policy is inferred here.

## Verification coverage

Sixteen new tests exercise:

- one detector invocation for all M1 consumer views;
- full source-candle and close-time preservation;
- LONG/SHORT and M1/M5 profile handling, with M5 rejected by the M1 adapter;
- mismatched setup, sequence, snapshot, context, time, integrity or event IDs;
- changed geometry, profile, symbol, direction and source candles;
- cross-setup candidates with identical numeric POI bounds;
- stale, expired, invalidated or not-yet-retested evidence;
- provisional POI rejection;
- revised immutable analysis/evidence rejection;
- persistence/reopen/retry without redetection or extra writes;
- rejection of missing/terminal persistent state despite an intact old candidate;
- no publication permission and no fabricated trade-price fields.

The generic full V3.3 discovery command automatically includes this module:

```powershell
python -m unittest discover -s tests -p 'test_agent_*v33*unittest.py' -v
```

## Current stage

The user supplied VPS test and push transcripts for baseline commit
4c5dfaf39b2e3b49d3ed85c592131dee89cf3773: 10 baseline pytest checks,
10 recovery-harness checks and 71 V3.3 checks passed, and the guarded push
confirmed that commit on the remote development branch. Some baseline checks
repeat between suites. These transcripts do not verify the new adapter commit.

The new adapters need external VPS verification, broker-calibrated fixture
acceptance and staged replacement tests against actual runtime entry points.
Signal Watcher remains disconnected. Production deployment and live execution
remain outside this change. V3.3 phase-wide PASS is not claimed.
