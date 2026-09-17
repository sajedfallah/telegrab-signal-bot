# NEXUS Agent System V1 — Reuse Audit

Status: Phase 0 source audit
Branch: `feature/nexus-agent-system-v1`

## Decision

V1 extends the existing NEXUS market stack. It does not replace Telegram, Mini App, Signal Engine, AutoTrade, MT5 execution, lifecycle, trailing, licensing, payment, or production news publishing.

## Reuse map

### MT5 market truth — REUSE

- `mt5/NEXUS_MarketFeed/NEXUS_MarketFeed.mq5`
- `app/market_candles.py`
- `app/autotrade/market_quote_runtime.py`
- `app/autotrade/symbol_registry.py`

These are the preferred production-read-only inputs for XAUUSD/US30 and any supported MT5 symbol. `MarketSnapshot` must consume real MT5 Bid/Ask and closed candles when this source is available. It must never synthesize an executable quote from candles.

Existing freshness/future-skew validation remains authoritative. Agent code adds stricter fail-closed checks; it does not weaken existing checks.

### ICT analysis — REUSE LOGIC, REMOVE PUBLIC-DATA DEPENDENCY FOR AGENT CORE

- `app/services/market_ict_service.py`
- `app/analysis_center.py`
- `app/analysis_quadrant_patch.py`

Reusable deterministic logic:
- 1H structure/bias
- previous-day bounds and liquidity
- 15M FVG detection
- 15M order-block approximation
- 5M sweep + MSS confirmation
- Daily Quadrant semantics: HTF context, never entry by touch alone

The current public-editorial ICT service fetches OHLC from an external HTTP source. The Agent System must instead accept an immutable `MarketSnapshot`; provider access belongs in adapters, not inside specialist agents.

### News / macro context — REUSE AS READ-ONLY INPUT

- `app/services/professional_news_engine.py`
- `app/services/market_brief_service.py`
- `app/services/market_editorial_service.py`

Reusable concepts:
- GOLD/BTC/DOW relevance detection
- source tiering
- macro/volatility/freshness scoring
- story deduplication

Agent V1 does not alter public-channel publishing thresholds or routing. News assessment is a separate read-only specialist output.

### Existing risk/execution — PRESERVE, DO NOT COUPLE IN PHASE 0/1

- `app/autotrade/risk_firewall.py`
- `app/risk_admin_runtime.py`
- `mt5/NEXUS_AutoTrade_UI65/Core/Include/RiskManager.mqh`
- existing AutoTrade execution/lifecycle modules

The Agent System gets its own pre-signal deterministic `RiskGate`. It may veto a candidate but cannot place orders. Existing execution-side risk remains authoritative if/when a later validated candidate is integrated.

### Test conventions — REUSE

Keep tests under `tests/`, deterministic, fixture/replay friendly, and independent of network/production services. Phase 0 tests cover contracts and state transitions before any provider or LLM integration.

## New isolated package boundary

Create `app/agent_system/` with no import-time side effects and no route registration:

- `contracts.py` — immutable schemas/contracts
- `state_machine.py` — deterministic lifecycle validation
- later: `snapshot_adapter.py`, `scanner.py`, `agents/`, `supervisor.py`, `risk_gate.py`, `journal.py`

No code in this package may publish Telegram messages, mutate AutoTrade state, issue MT5 commands, or read secrets directly.

## State machine

Primary progression:

`SCAN -> WATCH -> ARMED -> SIGNAL_CANDIDATE`

Terminal/side states:

`WAIT`, `CANCELLED`, `NO_TRADE`

`SIGNAL_CANDIDATE` is not an executable signal. A later phase must explicitly bridge a validated candidate into the existing Signal Engine.

## External repository policy

QuantDinger, FriesTrader, finance-skills, trading-skills, AgenticTrading, NautilusTrader, FinGPT and other reviewed repositories remain references or isolated future services. Phase 0 vendors none of them.

## Phase 0 acceptance

- contracts validate direction/state/freshness inputs
- snapshots are immutable
- stale/missing data can be represented explicitly
- state transitions reject unsafe jumps
- NO_TRADE is first-class
- no production route, Telegram publication, or AutoTrade execution changes
