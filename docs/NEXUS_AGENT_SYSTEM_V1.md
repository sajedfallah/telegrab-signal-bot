# NEXUS Agent System V1

Status: Phase 0 / architecture baseline
Branch: `feature/nexus-agent-system-v1`
Base: `feature/live-charts-v1` @ `59fcfec350449e9f5156348b765299428540f730`

## Safety boundary

This work EXTENDS NEXUS. It does not rewrite the existing Telegram, AutoTrade, MT5, trailing, lifecycle, license, payment, or Mini App runtime paths.

Production remains untouched. No agent receives unrestricted production or MT5 execution access.

## V1 objective

Build a deterministic-first market-intelligence pipeline for XAUUSD, US30/DOW, BTC and SOL which can produce `WATCH`, `SIGNAL_CANDIDATE`, `WAIT`, or `NO_TRADE`. Live execution is explicitly out of scope for V1.

## Pipeline

1. `MarketSnapshot` — normalized market state from approved providers. MT5/Broker remains source of truth for executable Gold/Forex/index prices.
2. `MarketScanner` — cheap deterministic pre-filter. Specialist agents are not invoked unless a market event/zone/condition is interesting.
3. Specialist analysis:
   - ICT: 1H bias -> 15M DP/FVG/OB/Daily Quadrant -> 5M trigger.
   - Ichimoku.
   - Elliott.
   - Macro.
   - News/Sentiment.
   - Market Regime.
4. `Supervisor` — detects agreement, disagreement and missing evidence. It must not invent scores or market facts.
5. `RiskGate` — deterministic veto layer. Checks data freshness, session, event risk, spread, RR, exposure/daily-loss policy and required entry confirmation.
6. `DecisionJournal` — stores inputs, every specialist output, supervisor result, risk decision and eventual outcome.

## Required state machine

`SCAN -> WATCH -> ARMED -> SIGNAL_CANDIDATE`

Any state may transition to `WAIT`, `CANCELLED`, or `NO_TRADE` when evidence/risk requirements fail.

V1 does not automatically convert `SIGNAL_CANDIDATE` into an executable AutoTrade signal.

## Core contracts

### MarketSnapshot

- `snapshot_id`
- `symbol`
- `as_of`
- `source`
- `timeframes`
- `bid/ask/last` when available
- `session`
- `scheduled_events`
- `news_context`
- `data_freshness_ms`

### AgentAssessment

- `agent_id`
- `symbol`
- `snapshot_id`
- `direction`: `LONG | SHORT | NEUTRAL`
- `confidence`: calibrated numeric value, nullable until calibration exists
- `evidence[]`
- `invalidations[]`
- `missing_data[]`
- `created_at`

### SupervisorDecision

- `state`: `WATCH | ARMED | SIGNAL_CANDIDATE | WAIT | NO_TRADE | CANCELLED`
- `direction`: nullable
- `agreement`
- `conflicts[]`
- `required_confirmation[]`
- `explanation`

### RiskDecision

- `allowed`
- `hard_blocks[]`
- `warnings[]`
- `rr`
- `risk_policy_version`

## Scoring rule

V1 must not assign arbitrary weights such as ICT=40% or Macro=20%. Initial scores are evidence labels/heuristics only. Production weights require historical validation plus forward/paper evidence. Calibration data is segmented by symbol, session and market regime.

## Decision Journal

Journal both trades and no-trades. Minimum record:

- market snapshot
- scanner trigger
- all specialist assessments
- supervisor decision
- risk decision
- signal/no-trade state
- proposed entry/SL/TP when present
- later MFE/MAE/outcome/PnL when measurable

This becomes the dataset for NEXUS Lab and future model training.

## External project policy

External repositories are references or isolated services, not code dumped into NEXUS core:

- OpenBB: candidate auxiliary financial/macro data service; broker/MT5 remains execution-price authority.
- awesome-llm-apps / 500-AI-Agents: architecture/pattern references only.
- FinGPT: candidate financial NLP/sentiment component after isolated evaluation.
- NautilusTrader: research/backtest/simulation candidate, separate from current AutoTrade execution.
- AgenticTrading: trading-agent evaluation concepts/lab reference.
- MoneyPrinterTurbo: later isolated content service.
- Transformers/Unsloth: later model/fine-tuning phase after sufficient NEXUS journal data exists.
- OpenHands: engineering automation only, isolated from production.

Licenses and transitive dependencies must be reviewed before any external code is vendored or deployed.

## Phase plan

### Phase 0 — current
- Freeze contracts and boundaries.
- Audit reusable existing Analysis Center, chart/live-data and news components.
- Add tests for schemas/state transitions before providers or LLMs.

### Phase 1 — Observation-only intelligence
- Implement snapshot/scanner/specialist interfaces/supervisor/risk/journal.
- Use fixtures/replay data first.
- No Telegram publication and no AutoTrade execution.

### Phase 2 — Real read-only data
- Attach MT5/Broker read path and selected auxiliary providers.
- Run shadow decisions and journal them.

### Phase 3 — Lab validation
- Historical replay/backtest and paper/forward evaluation.
- Calibrate specialist reliability by symbol/session/regime.

### Phase 4 — Human-reviewed signal candidate
- Surface candidate + evidence in admin/analysis workflow.
- Human approval remains required.

### Phase 5 — Controlled integration
- Only after validation gates pass, integrate approved decisions with existing Signal Engine.
- Existing Risk/AutoTrade lifecycle remains authoritative.

## V1 acceptance gates

- Existing NEXUS regression suite remains green.
- No production service restart/deploy as part of development.
- No synthetic executable Gold/Forex/US30 price.
- Every decision references a timestamped snapshot and evidence.
- Missing/stale data fails closed.
- `NO_TRADE` is a first-class valid result.
- RiskGate can veto every upstream agent/supervisor decision.
- Replay of the same immutable snapshot is deterministic at the orchestration/risk layer.
