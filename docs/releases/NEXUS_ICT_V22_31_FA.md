# NEXUS ICT Expert V22.31 — NEXUS TRAIL 07

**Release type:** MT5 Expert position-management integration  
**Profile:** `NEXUS_TRAIL_07 / NEXUS Smart Hybrid v2`  
**Date:** 2026-09-17  
**Tracking issue:** #47  
**Documentation PR:** pending assignment at first commit; updated after PR creation  
**Core backend/API release:** unchanged (`AutoTrade API 0.6.5`)  

---

## 1. Executive Summary

V22.31 ports the official NEXUS trailing profile 07 from the main NEXUS project into the current NEXUS ICT Expert management path. The release is focused on **position lifecycle behavior inside MT5**; it does **not** introduce a Backend, database, API, infrastructure, dependency, payment, Telegram routing, or Mini App breaking change.

The core model is:

`Entry → 1R Break-Even → TP1 30% → Hybrid Runner → TP2 30% → Final TP closes remaining volume`

The runner uses two independent stop candidates after TP1 is execution-confirmed:

1. latest confirmed Market Structure swing using `left=2/right=2`;
2. ATR(14) × 2 based on the last closed bar.

Only an improving stop is accepted. For BUY positions the stop may only increase; for SELL positions it may only decrease.

The Expert intentionally retains a stronger lifecycle gate than the source NEXUS implementation: **TP2 cannot complete before TP1 is execution-confirmed and Final TP cannot complete before TP2.**

---

## 2. Scope and Non-Scope

### In scope

- MT5 position management for newly opened ICT Expert positions.
- Profile snapshot and restart-safe lifecycle state.
- Break-even behavior.
- Partial-close behavior and retry policy.
- Structure/ATR hybrid trailing.
- Broker volume-step, minimum-volume, Stops Level and Freeze Level safety.
- Final target behavior.
- UI representation of active management profile.
- Documentation, migration and Demo QA procedure.

### Out of scope / unchanged

- NEXUS Telegram Bot business logic.
- FastAPI routes and payload models.
- SQLite schema and migrations.
- Payment, pricing, subscription and license entitlement rules.
- Mini App.
- Exchange AutoTrade / CCXT flow.
- Telegram channel/topic routing.
- Caddy/reverse-proxy configuration.
- Windows service topology.
- Docker/Kubernetes; no container platform is introduced by this release.

---

## 3. Source-of-Truth Review

The V22.31 behavior was mapped from the following files in the NEXUS repository:

- `app/autotrade/trailing_profiles.py`
  - declares `NEXUS_TRAIL_07`, version 2;
  - `break_even_r=1.0`;
  - `tp1_close_pct=30.0`;
  - `tp2_close_pct=30.0`;
  - `runner_pct=40.0`;
  - `runner_mode=MARKET_STRUCTURE_ATR_FALLBACK`;
  - `atr_period=14`, `atr_multiplier=2.0`;
  - `swing_left=2`, `swing_right=2`.
- `mt5/NEXUS_AutoTrade/Include/TrailingEngine.mqh`
  - break-even, partial stages, Structure and ATR runner logic;
  - monotonic stop movement;
  - per-signal throttling;
  - TP stage state.
- `mt5/NEXUS_AutoTrade/Include/TradeManager.mqh`
  - broker volume normalization;
  - execution-confirmed Partial Close;
  - execution-confirmed SL modifications;
  - full-close confirmation.
- `tests/test_v063_trailing_execution_truth.py`
  - static execution-truth contract checks.
- `NEXUS_V0.6.3_TRAILING_HARDENING_REPORT_FA.md`
  - operational hardening contract.

Repository main tree inspected during implementation: `ad2cacce4b10b28d768d740b08c36c429b16858c`.

---

## 4. Complete Behavioral Specification

### 4.1 Immutable anchors

At position creation the following data is treated as immutable management state:

- actual broker fill Entry;
- initial Stop Loss;
- initial risk distance `R = abs(Entry - InitialSL)`;
- initial broker volume;
- TP1 / TP2 / TP3 target prices;
- management profile mode/version.

V22.31 also persists the profile identity and key percentages in terminal Global Variables so a terminal restart does not silently reinterpret an existing trade under a different management model.

### 4.2 Break-even

Activation threshold:

`currentR >= 1.0`

For Trail07 the requested SL is exactly Entry. The configurable legacy Break-Even offset is intentionally not applied to Trail07 because the source profile defines pure break-even.

The resulting stop still passes Broker Stops/Freeze validation before submission.

### 4.3 TP1

Trigger: price reaches the Expert TP1 level.

Requested close volume:

`InitialVolume × 30%`

Volume is normalized down to the broker `SYMBOL_VOLUME_STEP` and must satisfy:

- close volume >= `SYMBOL_VOLUME_MIN`;
- remaining volume is either zero for a full close or remains >= minimum volume;
- terminal position volume must actually decrease after the trade request.

Only after the live volume change is confirmed does `TP1 Done` become true.

### 4.4 Runner activation

Runner management becomes eligible **only after TP1 has been execution-confirmed**.

That rule prevents Structure or ATR movement from being treated as evidence that a partial target completed.

### 4.5 Structure candidate

Profile constants:

- `swing_left = 2`
- `swing_right = 2`
- closed bars only.

For BUY:

- locate the most recent confirmed swing low;
- candidate stop must be above current SL to be accepted;
- candidate must remain below current market by broker minimum distance.

For SELL:

- locate the most recent confirmed swing high;
- candidate stop must be below current SL to be accepted;
- candidate must remain above current market by broker minimum distance.

### 4.6 ATR candidate

Profile constants:

- ATR period: 14;
- multiplier: 2.0;
- source: last closed bar.

BUY candidate:

`Bid - ATR(14)[1] × 2`

SELL candidate:

`Ask + ATR(14)[1] × 2`

The candidate is clamped against broker Stops Level / Freeze Level and is rejected unless it improves protection.

### 4.7 Hybrid selection

The source NEXUS engine applies Structure and then ATR using a monotonic `MoveSL` rule. The effective behavior is equivalent to accepting the tightest valid improving stop among the candidates encountered during the pass.

The Expert therefore guarantees:

- no stop regression;
- no crossing to the invalid side of market price;
- no duplicate unsafe modification merely because both candidates exist.

### 4.8 TP2

Trigger: price reaches TP2 **and TP1 is confirmed**.

Requested volume:

`InitialVolume × 30%`

The stage follows the same execution-truth rules as TP1.

After confirmed TP2, protection is not allowed to be worse than the TP1 anchor where broker geometry permits.

### 4.9 Final target / TP3

Trail07 keeps the final target as a real broker target for completion safety. When TP3/Final is reached after TP1 and TP2 confirmation, the Expert closes **all remaining volume**.

The 40% value is nominal. Broker-step rounding at earlier partials can make the actual runner slightly larger or smaller.

Example with volume step `0.01`:

- initial `0.10`;
- TP1 closes `0.03`;
- TP2 closes `0.03`;
- `0.04` remains for final target.

### 4.10 Partial failure and retry

A rejected or unconfirmed partial never advances the TP stage.

Backoff sequence:

`1s → 2s → 4s → 8s → 16s → 30s → 30s ...`

The retry is bounded to avoid aggressive server hammering while still recovering from transient trade-server conditions.

### 4.11 Small-volume behavior

With `min=0.01`, `step=0.01`:

| Initial volume | 30% raw | normalized partial | expected behavior |
|---:|---:|---:|---|
| 0.10 | 0.030 | 0.03 | valid |
| 0.04 | 0.012 | 0.01 | valid |
| 0.03 | 0.009 | 0.00 | invalid; retry, no fake TP completion |
| 0.01 | 0.003 | 0.00 | invalid; retry, no fake TP completion |

Operational implication: for deterministic 30/30/40 testing with a 0.01 volume step, `0.10` is the cleanest test volume.

---

## 5. Changelog / Defects Resolved

All items in this release are tracked under **Issue #47**. The documentation PR number is added after PR creation.

### Functional mismatches corrected from V22.30 legacy behavior

1. **Partial distribution mismatch**
   - Previous: 25/25/25 + runner.
   - V22.31 Trail07: 30/30 + nominal 40 runner.

2. **Runner activation mismatch**
   - Previous: trailing runner started only after TP3.
   - V22.31 Trail07: hybrid trailing starts after execution-confirmed TP1.

3. **Break-even semantics mismatch**
   - Previous: optional configurable offset.
   - V22.31 Trail07: exact Entry at 1R.

4. **Structure settings mismatch**
   - Previous: adaptive/dynamic pivot width in legacy path.
   - V22.31 Trail07: fixed 2/2 to match NEXUS profile snapshot.

5. **ATR semantics mismatch**
   - Previous: legacy runner mode behavior.
   - V22.31 Trail07: closed-bar ATR14×2.

6. **Lifecycle ambiguity on small lots**
   - V22.31 refuses to fake stage completion when broker min/step prevents 30% close.

7. **Runtime profile mutation risk**
   - Trail mode/version and key percentage semantics are snapshotted per new position.

8. **UI ambiguity**
   - Active Trail07 is displayed as `TRAIL NXS07`; legacy EXIT cycling no longer overrides Trail07 behavior for newly snapshotted positions.

### Safety retained from earlier hardening

- Partial-close confirmation by real volume reduction.
- Full-close confirmation by position disappearance.
- SL/TP modification confirmation.
- OWNER_TF / OWNER_INST / heartbeat multi-instance protection.
- Hard post-fill risk cap.
- Atomic entry lock.
- Projected margin validation.
- AutoTrade default remains explicit/safety-gated.

---

## 6. Actions Taken

### Phase 1 — source audit

1. Located `NEXUS_TRAIL_07` in backend profile definitions.
2. Audited MT5 `TrailingEngine.mqh` behavior.
3. Audited `TradeManager.mqh` execution truth for Partial/SL/Close.
4. Reviewed static tests and hardening notes.
5. Mapped differences against V22.30 Expert management.

### Phase 2 — implementation

1. Added Trail07 enable input.
2. Added immutable constants for profile v2.
3. Added per-position management mode/version snapshot.
4. Added 30% TP1 and 30% TP2 partial model.
5. Added exact 1R break-even.
6. Added 2/2 closed-bar structure trailing.
7. Added closed-bar ATR14×2 trailing.
8. Added hybrid monotonic selection.
9. Added retry state and bounded exponential backoff.
10. Added final remaining-volume close at TP3.
11. Preserved sequential TP safety stronger than source implementation.
12. Added UI management label and cleanup state.

### Phase 3 — static validation

Verified source markers for:

- profile version;
- profile enabled default;
- BE 1R;
- TP1/TP2 percentages;
- runner percentage;
- ATR period/multiplier;
- swing 2/2;
- post-TP1 runner gate;
- sequential TP gate;
- final close;
- exponential retry;
- execution-truth call path;
- profile persistence;
- source brace balance.

---

## 7. Backend Documentation

### 7.1 Release impact

**No Backend source modification is required by V22.31.**

The profile is executed locally by the current ICT Expert. The existing NEXUS Core remains compatible and continues to expose AutoTrade API version `0.6.5`.

### 7.2 Current API contract retained

The current backend already exposes the AutoTrade control plane under `/api/v1/autotrade` and admin routes under `/api/v1/admin`.

Key routes retained unchanged include:

- `GET /api/v1/autotrade/health`
- `POST|GET /api/v1/autotrade/activate`
- `POST|GET /api/v1/autotrade/license/check`
- `POST|GET /api/v1/autotrade/heartbeat`
- `GET /api/v1/autotrade/signal-receipt`
- `GET /api/v1/autotrade/command-receipt`
- `POST /api/v1/autotrade/account-change`
- admin account-change review routes
- `POST /api/v1/admin/mt5/signals`

MT5 compatibility GET endpoints remain available because some terminal/build combinations are less reliable when POSTing JSON to localhost Uvicorn.

### 7.3 Data models

No Pydantic model changes are required. Existing backend models already support:

- up to 10 targets;
- `trailing_code` and `trailing_config`;
- `break_even_r`;
- `atr_period`, `atr_multiplier`, `activation_r`;
- `tp1_close_pct`, `tp2_close_pct`, `runner_pct`;
- `swing_left`, `swing_right`.

### 7.4 Database

No migration is introduced by this release.

- no table change;
- no index change;
- no new query path;
- no backfill.

The Expert-specific V22.31 runtime state is persisted in MT5 terminal Global Variables. It does not modify `nexus_bot.db`, `nexus_fsm.db`, or AutoTrade backend tables.

### 7.5 Business logic

Backend pricing, subscriptions, license entitlement, account binding, receipt verification and publication rules are unchanged.

Broker-confirmed receipt logic in the current backend remains authoritative for backend-visible signal states; V22.31 does not weaken this contract.

---

## 8. Infrastructure / Server Documentation

### 8.1 Environment topology

No topology change is required for V22.31.

Current documented runtime remains Windows-oriented:

- Telegram Bot process;
- AutoTrade FastAPI/Uvicorn process;
- MT5 terminal/Expert process;
- existing reverse proxy/domain layer where configured.

### 8.2 Development

No new local service is required.

Python environment remains installed with:

`python -m pip install -r requirements.txt`

MT5 source still requires MetaEditor for actual compilation.

### 8.3 Staging / Demo

This release must first run on a Demo MT5 account.

Recommended staging layout:

- one XAUUSD M5 chart for initial rollout;
- V22.31 attached;
- Algo Trading enabled;
- a controlled test volume such as 0.10 when step=0.01;
- Journal retained for TP/Retry/SL audit.

### 8.4 Production

Production rollout should be blocked until all Demo gates in the runbook pass.

A safe deployment sequence is:

1. backup prior `.ex5`, `.mq5`, `.set` and terminal profile;
2. compile V22.31;
3. Demo smoke test;
4. verify no unmanaged open production position would be inherited unexpectedly;
5. replace Expert during a controlled maintenance window;
6. monitor Journal and first full trade lifecycle.

### 8.5 CI/CD

No workflow file is modified by V22.31.

Current Mini App GitHub Actions pipeline uses:

- Ubuntu latest;
- Python 3.11;
- `actions/checkout@v4`;
- `actions/setup-python@v5`;
- dependency installation from `requirements.txt`;
- Python `compileall`;
- `pytest tests/test_miniapp_api.py -q`.

**Important gap:** MetaEditor/MQL5 compile is not currently part of GitHub Actions. V22.31 therefore cannot be called compile-verified from CI alone.

### 8.6 Containerization

No Dockerfile/Kubernetes deployment is introduced or required by this release. If containerization is added later, MT5 still requires a Windows-compatible execution strategy or a separately managed terminal host.

---

## 9. Integration & Communication

### 9.1 Service topology

The repository is a modular monolith around Python/Telegram plus an AutoTrade API and MT5 client. V22.31 changes only the local Expert lifecycle manager.

### 9.2 Protocols

Existing communication remains HTTP/REST between MT5 and FastAPI for the AutoTrade subsystem.

No gRPC, GraphQL, WebSocket, Redis Pub/Sub or message queue is introduced by this release.

### 9.3 Authentication headers

Current AutoTrade control-plane behavior continues to use license/account identity headers and admin headers for privileged mode. V22.31 does not change them.

### 9.4 Telegram

No publication routing change is introduced.

Free/VIP routing, topic routing and signal receipts remain Core concerns outside this release.

### 9.5 External APIs

No new external provider is introduced by V22.31.

Existing repository integrations can include Telegram, pricing/rate providers, Gemini-compatible AI endpoints, exchange APIs through CCXT and the NEXUS AutoTrade API; none are modified by this Expert release.

---

## 10. Dependencies

No dependency was added, removed or upgraded by V22.31.

Current `requirements.txt` remains:

| Package | Version constraint | Role |
|---|---|---|
| aiogram | `3.29.1` | Telegram bot |
| aiodns | `>=3.2,<4` | async DNS |
| python-dotenv | `1.0.1` | env configuration |
| tzdata | `2026.3` | timezone database |
| Pillow | `11.3.0` | image/report rendering |
| arabic-reshaper | `>=3,<4` | Persian/Arabic shaping |
| python-bidi | `>=0.6,<1` | bidi rendering |
| fastapi | `0.128.2` | AutoTrade/API backend |
| uvicorn | `0.48.0` | ASGI server |
| httpx | `>=0.27,<1` | HTTP client |
| cryptography | `>=43,<47` | encrypted exchange credentials |
| ccxt | `>=4.4,<5` | exchange integration |

MQL dependencies remain standard MetaTrader libraries and existing local include files. No third-party MQL library is introduced.

---

## 11. Security Notes

### Unchanged backend security

- customer AutoTrade requires valid license/account authorization;
- admin mode remains gated by server-side account allow-list/token;
- admin token comparison in backend uses constant-time `hmac.compare_digest` in current API code;
- real secrets remain `.env` values and must never be committed.

### Expert safety

- Trail07 does not bypass existing trade ownership checks;
- no SL candidate may weaken current protection;
- broker minimum/freeze geometry is respected;
- partial state is execution-confirmed;
- restart recovery uses persisted state;
- no credential is added to MQ5 source as part of this release.

### Operational security

- do not publish `.env`, license values, admin token, exchange key or account secrets in screenshots/log attachments;
- compile artifacts should be distributed through the existing controlled AutoTrade delivery path;
- Demo validation is mandatory before production activation.

---

## 12. Migration Guide — V22.30 → V22.31

### 12.1 Pre-upgrade

1. Record all open positions, ticket IDs, current SL/TP and remaining volume.
2. Save V22.30 `.mq5`, `.ex5` and `.set` as rollback artifacts.
3. Save a screenshot of EA Inputs.
4. Verify broker `SYMBOL_VOLUME_MIN` and `SYMBOL_VOLUME_STEP` for test symbol.
5. Prefer no open position during binary replacement.

### 12.2 Compile

1. Copy `NEXUS_ICT_V22_31_NEXUS_TRAIL_07_OWNER.mq5` and required include files into the MT5 Experts directory.
2. Open in MetaEditor.
3. Compile.
4. Do not advance if any compile error exists.
5. Record compiler output in the release evidence.

### 12.3 Demo deployment

1. Open XAUUSD M5.
2. Attach V22.31.
3. Keep AutoTrade controlled/off until initialization logs are checked.
4. Confirm Journal reports `management=NEXUS_TRAIL_07`.
5. Enable Algo Trading and Expert AutoTrade only on Demo.
6. Execute at least one full lifecycle.

### 12.4 Acceptance checks

- at 1R, SL goes to exact Entry;
- TP1 closes 30% of initial volume where broker step permits;
- only after TP1 confirmation does hybrid trailing start;
- TP2 closes another 30%;
- SL never moves backward;
- TP3 closes all remaining volume;
- restart after TP1 does not repeat TP1;
- invalid partial produces retry, not fake completion.

### 12.5 Production rollout

Only after Demo acceptance:

1. schedule maintenance;
2. stop/reload Expert safely;
3. attach compiled V22.31;
4. verify inputs;
5. monitor first trade lifecycle in real time;
6. retain rollback artifact until several clean lifecycles are completed.

---

## 13. Rollback Guide

Rollback target: V22.30 known-good binary/preset.

1. Disable new entries.
2. If an active V22.31 trade exists, do not blindly swap lifecycle engines mid-position.
3. Decide whether to let V22.31 finish the active trade or manually close it according to operator policy.
4. Remove V22.31 from the chart.
5. Restore V22.30 EX5 and matching preset.
6. Restart/reattach and verify ownership/runtime state before reenabling entries.

Never claim a rollback is safe for an already partially managed position without checking actual current volume and stop state.

---

## 14. QA and Quality Gates

### Static validation already completed

- all Trail07 profile constants present;
- new profile default enabled;
- 1R break-even branch present;
- 30% TP1/TP2 paths present;
- 40% runner metadata present;
- ATR14×2 path present;
- swing 2/2 path present;
- hybrid starts after TP1;
- TP2 gated by TP1;
- final close path present;
- exponential backoff present;
- execution-truth partial confirmation retained;
- snapshot persistence present;
- brace balance passed.

### Tests still required

1. MetaEditor compile: target 0 errors / 0 warnings.
2. Demo XAUUSD BUY lifecycle.
3. Demo XAUUSD SELL lifecycle.
4. 0.10 volume 30/30/40 check.
5. 0.04 volume normalization check.
6. 0.03 invalid-partial retry check.
7. Restart after TP1.
8. Broker Invalid Stops / Freeze Level scenario.
9. Requote/price-change handling.
10. Multiple timeframe instances / ownership safety.
11. Netting vs hedging account behavior if both account types are supported in production.

### Test coverage

No MQL5 line/branch coverage percentage is currently available. Do not infer a numeric coverage value from Python pytest counts.

The existing repository test `tests/test_v063_trailing_execution_truth.py` remains a useful behavioral contract reference for the original NEXUS AutoTrade trailing engine, but it is not a substitute for compiling and forward-testing the V22.31 ICT Expert artifact.

---

## 15. Observability and Troubleshooting

Key Journal signals introduced/expected by the Trail07 path include:

- `[NEXUS][TRAIL07][TP1]`
- `[NEXUS][TRAIL07][TP2]`
- `[NEXUS][TRAIL07][FINAL]`
- `[NEXUS][TRAIL07][PARTIAL_RETRY]`

For a lifecycle incident capture:

- symbol/timeframe;
- position ticket/identifier;
- initial volume;
- current volume;
- Entry/Initial SL/current SL;
- TP1/TP2/TP3;
- broker min/step/stops/freeze;
- relevant Journal lines;
- whether terminal restarted;
- whether multiple Expert instances were attached.

Do not include credentials or admin tokens in incident evidence.

---

## 16. Known Limitations

- 30% partial cannot be represented for every broker volume/step combination.
- Small volume such as 0.01 with 0.01 step cannot physically perform a 30% partial.
- MT5 MetaEditor compile is not part of current CI.
- This documentation PR does not itself distribute a binary EX5.
- Current V22.31 lifecycle is designed around three Expert targets (TP1/TP2/TP3), while the broader NEXUS backend supports up to TP10.
- Actual runner percentage can differ slightly from 40% due to broker volume rounding.

---

## 17. Stakeholder Summary

### Development

Primary change is an MT5 lifecycle profile port. Backend is unchanged. Focus code review on execution truth, volume normalization, runner activation order and state persistence.

### DevOps

No service/database migration. Main operational requirement is controlled MetaEditor compile, Demo rollout, evidence collection and rollback artifact retention.

### Product / non-technical stakeholders

The trade manager now follows the NEXUS Smart Hybrid profile consistently: protect at 1R, realize part of the trade twice, then let the remaining position run with adaptive protection until the final target.

---

## 18. Related Files

- `CHANGELOG.md`
- `README_FA.md`
- `docs/wiki/NEXUS_ICT_V22_31_RUNBOOK_FA.md`
- `app/autotrade/trailing_profiles.py`
- `mt5/NEXUS_AutoTrade/Include/TrailingEngine.mqh`
- `mt5/NEXUS_AutoTrade/Include/TradeManager.mqh`
- `tests/test_v063_trailing_execution_truth.py`
- Issue #47
