# Shared closed-candle detector — opt-in research migration

`shared_detector_v33` supplies one structural sequence algorithm for M1 and M5.
It is not imported by the runtime Fast Scalp, tracker, full gate or Signal Watcher.
Those legacy paths are unchanged; their known disagreements remain migration
blockers until callers are explicitly moved through verified adapters.

## Inputs and exact rules

- An immutable Setup contains symbol, direction, trigger timeframe, original POI
  bounds/origin, explicit context reference, invalidation price and expiry.
- An EvidenceFrame contains immutable closed broker candles and a synchronized
  decision clock/reference. The detector revalidates provenance, contiguity,
  quote geometry, context and candle-close availability. Actual broker calibration
  acceptance remains a separate gate; the detector cannot authenticate a feed.
- The caller must supply one explicit sweep open timestamp. A newer sweep does
  not replace it. A new anchor/policy has a distinct sequence identity, and the
  persistence bridge rejects mixing that sequence into existing core evidence.
- Sweep: wick penetration and close reclaim of the preceding 12-bar liquidity
  extreme, overlapping the original POI. Equal extremes choose the latest source
  candle. The liquidity window is configurable and recorded in sequence identity.
- MSS reference: the latest strictly confirmed pivot available before the sweep.
  Default left/right confirmation width is two bars. Equal highs/lows do not form
  strict pivots. A pivot whose level was already broken by a close before/at the
  sweep is ineligible. Future candles cannot alter this pre-sweep reference.
- MSS: a strictly later closed candle crosses that exact swing level.
- Displacement: the earliest directional body meeting the Setup ratio against
  the mean absolute body of 12 prior candles. Default ratio 1.3 is an experimental
  research policy, not a calibrated performance claim. Same-candle MSS and
  displacement are allowed only by the existing explicit Setup exception.
- FVG: the earliest eligible directional three-candle gap whose first candle is
  at/after displacement; the middle body must agree with direction. The actual
  boundaries and origin candles are preserved. A gap formed before MSS cannot
  substitute for this event.
- Retest: a later closed candle overlaps that exact FVG. This is structural
  retest evidence, not an executable entry or rejection-candle model.
- Every later close is checked against the Setup invalidation price. Terminal
  invalidation or the absolute deadline supersedes a previously observed retest.
- Closed-series freshness defaults to at most two trigger periods since the last
  closed candle; stale or incomplete evidence never promotes a setup.

All thresholds are explicit research definitions, not evidence of profitability.
HTF bias, POI qualification, entry geometry and risk gates are not decided here.
Even a complete sequence stops at RETEST_CONFIRMED, with independent gates still
required. A provisional POI cannot gain entry/publication authority through this
module.

## Evidence and persistence

Detected event IDs hash the setup/anchor/policy, state and exact typed evidence.
Each later event references its preceding event ID. Snapshot references do not
change an already confirmed structural event ID. Incremental prefix tests verify
that later observations extend the same event prefix without future confirmation.

`apply_research_sequence` requires an existing isolated lifecycle Setup whose
location has already reached POI_TOUCHED using independent caller evidence. It
does not manufacture DISCOVERED/selection/approach/touch transitions. It maps the
detector's event references onto actual persisted event IDs, checks every stored
prefix and commits new core events through the existing transactional validator.

Each event is committed independently. If processing is interrupted, a retry
validates and resumes the exact committed prefix; this is not an all-events batch
transaction. Missing/revised prefix evidence, a different sweep or changed policy
fails closed. Exact closed invalidation is persisted through the store's monitor;
terminal states cannot reactivate. The bridge never appends ENTRY_READY or
SIGNAL_PUBLISHED, reserves delivery or imports a transport/order module.

## Migration status and verification

Fifteen new tests cover complete LONG/SHORT sequences on M1/M5, exact source and
event references, incremental no-lookahead behavior, fixed anchor after a newer
sweep, stale/foreign/unclosed/gapped inputs, strict pivot confirmation, previously
broken swings, pre-MSS gap rejection, the explicit same-candle exception, research
POI boundaries, restart/retry persistence and terminal invalidation.

The old detector characterization tests remain in the full suite. Their passing
assertions continue to expose differences in the old algorithms. They are not
an equivalence PASS for production callers. No runtime publication behavior has
been changed, and no real broker replay or strategy performance is claimed.

Run the existing full regression command; its discovery pattern automatically
includes the shared-detector tests:

```powershell
python -m unittest discover -s tests -p 'test_agent_*v33*unittest.py' -v
```

Next gates: external verification of this new commit; broker-calibrated fixture
acceptance; explicit adapters for the three old consumers with exact-event
comparison; preserved independent risk/publication gates. Signal Watcher remains
disconnected until these gates pass.
