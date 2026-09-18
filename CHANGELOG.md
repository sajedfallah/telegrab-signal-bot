# Changelog

این Changelog برای مسیر **NEXUS ICT Expert** از V22.31 به بعد است.

## [V22.46] — 2026-09-18 — Deep Research Telemetry + Analytics Viewer
### Added
- Daily CE research: origin candle, CE25/50/75, Wick strength, age, touch count, penetration.
- Sweep → MSS → FVG → Signal timing.
- Displacement and sweep-depth metrics.
- PDH/PDL/Asia liquidity map.
- Volatility percentile.
- Post-signal horizon dataset: 1/3/5/10/20 bars.
- Time-to-1R / 2R / SL.
- Counterfactual Trail07 vs fixed TP / alternate BE.
- Analytics Viewer labs: Signal / CE / Sequence / Timing / Execution / Management / Data Quality.
- Viewer fully Persian and RTL.

### Boundary
- No new Signal filter or Hard Gate.
- No automatic weight change.
- Private MQ5 artifact not committed publicly because of runtime-sensitive configuration.

### QA
- Static source checks: PASS.
- MetaEditor compile: required at test start.
- Demo forward test: 2026-09-18 → 2026-09-25.

## [V22.45] — 2026-09-18 — FileWrite Fix
- Signal snapshot writer moved from oversized `FileWrite(...)` calls to safe CSV string writer + `FileWriteString`.
- Header/data column alignment statically checked.
- User compiled and loaded the EA on Demo.
- Telegram connectivity verified after MT5 WebRequest permission setup.

## [V22.44] — 2026-09-18 — Compile Order Fix
- `g_executionSignalContext` declaration moved after full `SignalData` definition.
- Cascading reference/enum compile errors resolved.

## [V22.43] — 2026-09-18 — Analytics Viewer + Persian RTL Telegram
- Local Analytics Viewer.
- Weekly analytics report.
- Telegram Signal/Open/Update/Close/Reject/Test messages Persian + RTL.
- Parent/reply lifecycle retained.

## [V22.42] — 2026-09-18 — Observability Data Lake
- Signal snapshot CSV.
- Lifecycle events CSV.
- Telegram delivery CSV.
- Evaluated/Armed/Invalidated/Expired/Confirmed funnel.
- Server/UTC/New York timestamps.
- Broker/runtime/candle/volume/POI/FVG/OB/OTE telemetry.
- No new Signal filter.

## [V22.41] — 2026-09-18 — Intelligence & Analytics
- Result R.
- MFE/MAE.
- Performance attribution.
- CE vs No-CE.
- CE50 vs CE75.
- Reversal vs Continuation.
- Daily Intelligence Review.
- Observational adaptive-weight suggestion only; no auto-change.

## [V22.40] — 2026-09-18 — Signal Delivery Core
- Telegram Parent Signal + Reply lifecycle.
- Persisted parent message ID.
- Execution Reject Engine.
- Execution Quality separate from Signal Quality.
- Status model: Confirmed / Pending / Opened / Rejected / Expired / TP / Trail / Closed.

## [V22.39] — 2026-09-18 — Signal Quality Core
- Reversal / Continuation classification.
- Market Regime.
- Structured quality score.
- Daily CE / Quadrant integrated into scoring.
- Daily CE default +15; reversal CE bonus +5.
- Optional A+ reversal cap without Daily CE.

## [V22.38] — 2026-09-18 — Performance Core
- Reduced redraw/calculation pressure.
- UI responsiveness work.
- Runtime performance protections retained in later versions.

## [V22.37] — 2026-09-18 — Telegram Connection Test
- TG TEST button.
- Immediate Telegram HTTP attempt.
- HTTP 200 / retry / fail state.
- WebRequest diagnostics.

## [V22.36] — 2026-09-18 — Telegram Compile Fix
- Invalid `has_canonical_fvg` reference replaced with canonical `rule_fvg`.

## [V22.35] — 2026-09-18 — Professional Telegram Lifecycle
- Persian-ready professional templates.
- Signal/Open/Update/Close.
- Partial P/L.
- Current/new SL/TP values.
- Trail/BE/TP update events.

## [V22.34] — 2026-09-18 — Every Issued Signal
- Every live confirmed signal can be published even when AutoTrade execution later fails.
- Signal ID assigned at issuance.

## [V22.33] — 2026-09-18 — Dual Sizing
- Risk-percent sizing.
- Fixed-lot sizing.
- Fixed-lot risk-cap reject.
- Post-fill risk protection.

## [V22.32] — 2026-09-18 — Server AutoTrade Private
- Server-oriented AutoTrade build.
- M5 execution lock.
- Internal HTF context.
- Private Telegram runtime config.

## [V22.31] — 2026-09-17 — NEXUS_TRAIL_07
- NEXUS Smart Hybrid v2.
- BE at 1R.
- TP1 30% / TP2 30% / runner ~40%.
- Structure 2/2 + ATR14×2 after confirmed TP1.
- Monotonic SL.
- Execution-confirmed partial stages.
- Bounded exponential retry.
- Restart-safe position management snapshot.

## Next
V22.47 starts only after the V22.46 one-week review:
- Feature Combination Analyzer.
- Score Calibration.
- Confidence Engine.
- Failure Classification.
- MFE/MAE Optimization.
- Time Decay.
- Data Quality Guard.
- SQLite analytics store.
- Persian weekly Insight Report.
