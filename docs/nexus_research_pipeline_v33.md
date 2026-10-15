# Snapshot-to-persistent-gate research integration

`research_pipeline_v33.run_research_snapshot` connects the actual V3.3 components
in one opt-in path. No runtime caller imports it, and no existing watcher,
publication, order or production data source is changed.

## Flow

1. Copy and validate MarketSnapshot through evidence_frame. Explicit source
   closed_at metadata, fresh declared data, executable quote geometry, required
   trigger candles and an independently supplied context_ref are required.
2. Run the shared anchored detector once. Setup/context/provenance/chronology and
   closed-series freshness are validated before creating a lifecycle database.
3. For a new identity, require explicit LocationProof referencing actual closed
   candles in that frame. Selection, approach and touch must occur in order,
   before the sweep. Approach must be outside the zone within the caller's finite
   positive distance policy; the touch candle must overlap the original POI.
   These are research location observations, not inferred POI qualification.
4. Create or recover the explicitly isolated store. Existing immutable Setup,
   decision clock and location prefix are checked. A terminal setup cannot
   reactivate. An existing core prefix resumes without reconstructing location.
   New discovery records use the current snapshot observation time via the
   backward-compatible observed_at argument, rather than backdating discovery to
   the caller's logical Setup.created_at. Candle-origin times remain unchanged.
5. Append structural events via the shared persistence bridge. Retries compare
   exact source evidence and resume the matching committed prefix.
6. Create an evidence-only candidate only after a closed retest. Verify that
   candidate with persisted_full_ict_research against exact event IDs and current
   database state. No executable entry, SL or targets are manufactured.

## Result semantics

- STRUCTURE_VERIFIED: the research evidence candidate matches persisted structural
  state. This is not an ICT signal or a successful independent risk/MTF gate.
- WATCH: valid partial structural progress was recorded, but no complete candidate
  has passed the research gate.
- BLOCKED: invalid/missing input, inconsistent policy/evidence, provisional POI,
  clock conflict or persistent verification failure. No publication permission.
- TERMINAL: the stored identity is invalidated, expired, cancelled or previously
  published; it cannot be promoted by this call.

publication_allowed remains False. The pipeline does not call reservation,
Telegram, order or execution APIs. A terminal transition takes priority over an
old supplied candidate so that invalidation/expiration is still recorded.

## Write and failure boundary

Input and provided location proofs are validated before new setup advancement.
Invalid snapshot/metadata/context/policy input cannot create a new database.
An explicitly supplied mismatching candidate is rejected before advancement.

SQLite writes are transactional per event, NOT all-or-nothing for a whole
snapshot. A later processing failure can leave earlier validated events committed;
the result is BLOCKED, never structurally verified. Retrying resumes that exact
prefix. Error codes identify the failed processing stage without exposing paths
or credentials. Other known active setups are not reset or replaced.

This increment also fixes an independently reproduced policy-validation defect
in the research detector/analysis helpers: falsy non-policy inputs (0, False, {})
previously selected a default policy. Now only None selects the documented
default; other invalid types fail closed before pipeline persistence.

## Integration tests

Fifteen end-to-end tests use actual snapshot contracts, shared detector,
transactional temporary SQLite store and persistent research gate, without mocked
detector/store/gate components. All market data remains synthetic and isolated.

Coverage includes LONG/SHORT on M1/M5, both profiles sharing one synchronized
Snapshot/context/POI, invalid input before database creation, missing close
metadata, context mismatch, explicit location chronology, partial progress,
retries, forming retests, later invalidation/expiration, revised source candles,
foreign candidates, provisional POIs and retroactive snapshots. A child Python
process records a partial pipeline, exits, and a fresh caller completes the same
stored evidence prefix. SQL assertions verify no ENTRY_READY, SIGNAL_PUBLISHED
or publication reservation is created.

The existing regression runner automatically discovers these tests:

```powershell
python -m unittest discover -s tests -p test_agent_pipeline_v33_unittest.py -v
python -m unittest discover -s tests -p 'test_agent_*v33*unittest.py' -v
```

## External limitations

Synthetic integration success does not verify real broker clock calibration,
live feed metadata, actual HTF/POI policy, entry geometry or risk thresholds.
context_ref is an explicit reference provided by the caller, not substantive HTF
analysis. LocationProof does not certify POI quality. The current production
snapshot path still lacks required close metadata and is not connected here.

The user supplied VPS test/push evidence for parent 8b220c0: 10 baseline checks,
10 recovery-harness checks and 87 V3.3 tests passed, and that parent was pushed
to the remote development branch. These are historical parent results, not
evidence that this new pipeline commit was run on the VPS.

External verification of this commit, real broker-source acceptance, independent
risk/entry/publication gates and controlled runtime migration remain necessary.
Signal Watcher integration and phase-wide V3.3 PASS remain blocked.
