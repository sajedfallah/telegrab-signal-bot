# NEXUS baseline audit — 2026-10-15

PHASE: Baseline audit and V3.2 stabilization
STATUS: BLOCKED (runtime tests NOT VERIFIED)
BRANCH: feature/nexus-agent-system-v1
BASELINE COMMIT SHA: d973a0a91bc8199cc8ab38b8d165173b657f47e5
FILES CHANGED: docs/nexus_baseline_audit_20261015.md (this report only)

## Environment and provenance

The requested C:\NEXUS_AGENT_TEST directory does not exist on this host. A fresh isolated clone was acquired in the chat workspace under work/nexus. Initial git status was clean and the branch tracked origin/feature/nexus-agent-system-v1. A fresh clone cannot establish whether another machine has uncommitted work.

Recent commits: d973a0a independent mocked observations; bc9d0cb state mutation isolation; 37cb6ca valid fixture snapshot ID; 5f3b230 opt-in lifecycle documentation; a7a7b86 POI binding display.

No production paths, services, databases, credentials, Telegram clients or MT5 terminals were opened or modified. No application entry point was started. No publication or trading was attempted. The paused channel collection work was excluded.

## Evidence and blockers

1. setup_lifecycle_v32.py:17-96 stores a mutable latest evidence record, not an append-only event history. It permits first observation at any observed stage, has no versioned migration, expiry, event idempotency key or complete required state graph. It uses wall-clock timestamps at line 66. Recovery only restores selected fields when a lower stage reappears. POI rebinding invalidates, but disappearance of a currently eligible POI exits before loading stored state. These are V3.3 requirements, not established capabilities.
2. command_bot.py:40 invokes observe_configured for analysis. signal_watcher.py:53-90 never calls it; publication independently rescans structure. Its gate returns only POI bounds rather than setup/candle identities. Therefore publication cannot prove that its complete sequence is the same sequence used for the candidate plan. This is a release blocker.
3. signal_watcher.py:56,98 keeps duplicate fingerprints in memory; restart loses suppression. M5 uses the orchestrator's refreshed snapshot while M1 obtains a separate snapshot at line 76. There is no shared synchronized MTF version between the two decisions.
4. fast_scalp.py:50 uses midpoint/momentum H1 bias; agents/ict.py:19 uses pivots with a midpoint fallback. Fast Scalp _m1_sequence and FVG detection consume the supplied latest candle; ENTRY_READY at line 150 depends on current midpoint touching a gap, without proving a later closed retest. In contrast setup_tracker_v31.py:37 and full_ict_gate.py:63 discard the last trigger bar. Simply dropping the last row does not prove timestamps and feed completeness.
5. setup_tracker_v31.py permits a gap whose third bar coincides with MSS, while full_ict_gate.py starts the first gap bar at MSS. These disagree on post-MSS chronology. Both implement sweep and displacement independently of fast_scalp.py, which labels MSS displacement without its measurable body filter.
6. snapshot_adapter.py:17 excludes H4. Only H1/M15/M5 are mandatory at line 18. The configured shadow DB path is opened read-only, but an unset path invokes schema initialization on the app DB at lines 65-70. Any future runtime validation must set an isolated market DB explicitly. Actual broker H4 availability, session alignment and freshness cannot be established without an authorized feed export.
7. contracts.py validates quote geometry, finite quote prices and aware as_of, but candle dictionaries remain nested mutable data. It does not validate bar chronology, OHLC finiteness, candle close timestamps, per-timeframe source provenance or synchronized capture versions. snapshot_adapter.py validates some OHLC geometry but lacks explicit close evidence and rejects neither future timestamps nor all nonfinite candle values.
8. poi_scanner_v23.py:16-55 returns provisional zones without origin IDs/timestamps or chronological mitigation. These remain eligible for binding in lifecycle/gate code whenever quality is not TOO_WIDE, despite eligible_for_entry=False. OB detection in agents/ict.py:37 is an opposing candle before a large range, without a tested structural-break relationship. No freshness claim can yet be supported.
9. signal_engine.py derives stop/target candidates independently of the gate sequence; its FVG/target scans include the last supplied bar. A last-only quote can pass its initial quote helper but later executable-side conversion requires bid/ask. risk_gate.py:50-55 and watcher fast risk checks do not explicitly validate finite positive policy thresholds before comparison; the full gate adds its own finite minimum check. All mandatory risk validation needs one fail-closed contract.
10. scenario_v2.py:39 emits STRUCTURE_CONFIRMED_SHADOW numeric levels from Fast Scalp readiness without the full publication gate. The checklist therefore reflects a weaker confirmation definition than automated publication. journal.py:19 saves complete snapshots but no stable lifecycle event/publication IDs, and uses wall-clock recorded_at.
11. chart_renderer.py preserves the current-price badge without a full-width yellow line. However zone origins are rediscovered from displayed trigger candles and default to index zero at line 115, losing timeframe provenance. Line 142 expands thin zone display height. Future changes must preserve real boundaries and carry origin metadata rather than infer it from rendered evidence strings.

All fifteen files requested in the directive were inspected. No implementation was replaced before baseline verification.

## Coverage and executed checks

Existing tests include three V3.2 tests (missing POI blocks persistence, latest-stage recovery, changed POI invalidation), plus tracker, full-gate, contracts, risk, orchestrator, signal, POI, scenario and chart suites. The three lifecycle tests mock tracker and POI scanning; they do not establish integrated chronology, expiry, concurrent writes, schema migration or duplicate publication.

TESTS RUN:
- Bundled Python: python -m pytest tests/test_agent_setup_lifecycle_v32.py -q
- Result: exit 1, No module named pytest. No test was collected or executed.
- Isolated virtual environment creation succeeded.
- Dependency bootstrap: pip install --retries 0 --timeout 8 pytest pydantic python-dotenv
- Result: exit 1, files.pythonhosted.org HTTPS read timeout retrieving pytest metadata. Earlier default-retry attempt was interrupted after the same timeout.

TEST RESULTS: NOT VERIFIED. There is no evidence of a passing or failing V3.2 assertion. Missing test dependencies are an environment failure, not a reported strategy defect.

## Focused next implementation order

1. Restore the isolated test runtime; run the existing lifecycle suite and focused agent suites. Fix reproduced V3.2 failures first.
2. V3.3: implement transactional event storage, schema versions, immutable setup/POI bindings, validated transitions, idempotency, recovery, terminal invalidation and explicit expiry; test before scanner integration.
3. V3.4-V3.7: carry origin/close/eligibility evidence into POIs and shared structure/MTF contracts, unify M1/M5 candidate identity and independent gates, then persistent publication suppression. Preserve interfaces through adapters.
4. V3.8 requires actual historical MT5 data and spread/session provenance. No synthetic performance claim is acceptable.
5. V3.9 and V4.0 remain unverified until prior gates and actual replay/runtime observation pass.

REMAINING RISKS: The identified code-level gaps are unverified findings, not claims of executed invalid trades. No historical data or authorized shadow runtime was supplied. No phase is release-ready on this evidence.
NEXT PHASE: Resume V3.2 verification after package access is restored or an offline wheelhouse containing pytest and project test dependencies is made available. Obtain a read-only broker data export for subsequent integration/replay gates. Production deployment still requires explicit authorization.
