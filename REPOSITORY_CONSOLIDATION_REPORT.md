# REPOSITORY CONSOLIDATION REPORT

Repository: `sajedfallah/telegrab-signal-bot`  
Default branch: `main`  
Working branch: `refactor/repository-consolidation`  
Initial HEAD: `00336bc6e58eb434ed5ed89e95e0e444a4d6d72e`  
Audit date: 2026-10-06

## OVERALL STATUS

**PARTIAL**

The repository has been mapped and its canonical runtime/documentation contracts have been established. A verified duplicate repository-governance file was consolidated. Runtime code with material trading/Telegram/MT5 risk was not refactored without executable regression evidence.

## PROJECT MAP

| Domain | Status | Authoritative entrypoint / source |
| --- | --- | --- |
| Telegram Bot | ACTIVE | `run.py -> app.main.main` |
| Telegram Webhook | LEGACY/NOT ACTIVE | No canonical webhook runtime found in audited main; Telegram runtime uses polling. |
| Telegram Admin/User Actions | ACTIVE | `app/main.py` plus registered routers |
| Signal Agent | ACTIVE | `app/signal_agent/*` |
| Signal Creation / Persistence | ACTIVE | `app/main.py`, `app/db.py` |
| Telegram Signal Publication | ACTIVE | `app/main.py::_publish_signal` |
| Signal Lifecycle Replies | ACTIVE | `app/main.py::_reply_signal_update` and MT5 event processing |
| Mini App | ACTIVE | `miniapp/index.html`, `app/miniapp_api.py` |
| Admin Mini App | ACTIVE | `miniapp/admin.html`, `app/miniapp_admin_api.py` |
| API / BFF | ACTIVE | `app/combined_api.py` |
| FastAPI routes | ACTIVE | AutoTrade app + Mini App routers |
| Authentication / Telegram initData | ACTIVE/CANONICAL | `app/miniapp_api.py::_validate_init_data`, reused by admin API |
| Database layer | ACTIVE / PARTIALLY DISPERSED | `app/db.py` plus remaining direct SQL consumers |
| Signal lifecycle/events | ACTIVE | `app/main.py`, `app/db.py` |
| Execution / MT5 bridge | ACTIVE | `app/autotrade/api.py`, `app/autotrade/service.py` |
| Polling / Queue / Commands | ACTIVE | aiogram polling + DB-backed command/event paths |
| Position lifecycle | ACTIVE | AutoTrade API/service + DB live state |
| Result generation | ACTIVE | `app/main.py` |
| Background workers | ACTIVE | `app/main.py` |
| Configuration | ACTIVE / PARTIALLY DISPERSED | `app/config.py::settings`, env, limited direct getenv |
| Static frontend assets | ACTIVE / VERSIONED | `miniapp/index.html`, `miniapp/admin.html` and referenced assets |
| Deployment | ACTIVE / EXTERNAL PROXY NOT VERIFIED | Vercel frontend; VPS API runtime |
| Tests | ACTIVE | `tests/*`, GitHub Actions |
| Documentation | CONSOLIDATED | `README.md`, `ARCHITECTURE.md`, `CONFIGURATION.md`, `DEPLOYMENT.md`, `TESTING.md` |
| Legacy scripts/migrations/tools | MIXED / KEEP WITH NOTE | Requires individual usage/deployment/history evidence before removal |

## DISPERSION FOUND

### Database access

`app/db.py` is the intended DB Source-of-Truth, but raw SQL remains in runtime consumers including `app/main.py`, `app/miniapp_api.py`, `app/miniapp_admin_api.py`, and `app/autotrade/api.py`.

**Risk:** MODERATE/HIGH for consolidation because these queries participate in auth, payment, MT5 live state, signal state and lifecycle behavior.

**Action:** KEEP WITH NOTE. Migrate query-by-query only with focused regression coverage.

### Telegram runtime

The audited canonical runtime is aiogram polling from `app.main.main`. No competing active webhook handler was identified in the canonical startup path.

**Action:** KEEP polling as current authority. Do not introduce webhook/polling dual-runtime behavior.

### Signal formatting and MT5 payloads

Telegram signal captioning is centralized in `app/main.py`; AutoTrade publication imports the formatter rather than implementing a separate independent caption. MT5 signal payload creation is centralized in `app/autotrade/service.py::signal_to_payload`.

**Action:** KEEP.

### Authentication

Admin Mini App auth reuses `app/miniapp_api.py::_auth_user`; a separate conflicting Telegram initData validator was not identified in the audited canonical API path.

**Action:** KEEP.

### Frontend

The frontend contains many layered/versioned CSS/JS assets. The active HTML entrypoints reference multiple generations deliberately. Naming/version alone is insufficient evidence of dead code.

**Action:** NOT SAFE TO DELETE without complete reverse-reference and behavioral validation.

### Documentation

The root contains many historical release/audit reports with stale version-specific state. They are valuable historical evidence but were competing with current-state docs.

**Action IMPLEMENTED:** establish explicit canonical current-state documentation and mark historical reports as non-authoritative in README.

### GitHub PR template

Two case-variant PR template files existed with overlapping but different content:

- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/pull_request_template.md`

GitHub treats PR-template filenames case-insensitively, so the pair represented duplicate governance state.

**Action IMPLEMENTED:** merged requirements into the lowercase canonical file and removed the duplicate uppercase file.

## DUPLICATE IMPLEMENTATIONS

1. PR template governance: **MERGED**.
2. DB queries outside `app/db.py`: **DEFERRED / MODERATE-HIGH RISK**.
3. Frontend historical/versioned assets: **NOT PROVEN DEAD**.
4. Telegram initData validation: **NO conflicting active implementation found**.
5. MT5 payload formatter: **canonical shared implementation exists**.

## LEGACY PATHS

- Versioned reports and release notes: historical; not current Sources-of-Truth.
- `ARCHITECTURE_V7.md`: historical architecture snapshot; superseded for current-state navigation by `ARCHITECTURE.md`.
- Multiple Windows setup/start scripts: retained pending deployment-reference evidence.
- Versioned Mini App assets: retained pending reverse-reference and UI regression evidence.

## DEAD CODE

No production runtime code was deleted solely because it appeared old. No candidate met the full import/runtime/test/deployment/documentation/history deletion gate during this pass.

## CONFLICTING ROUTES

No proven duplicate FastAPI route collision was identified in the canonical combined app during the inspected route inventory. The combined app intentionally composes:

- root AutoTrade/MT5 routes,
- `/miniapp/api/*`,
- `/miniapp/api/admin/*`.

## CONFIGURATION ISSUES

- Canonical settings object exists in `app/config.py`.
- Some direct environment reads remain outside the settings object.
- Public URLs exist in documentation/example config and are not secrets.
- No secret value was intentionally emitted during this audit.

## DATABASE DISPERSION

Canonical DB module: `app/db.py`.

Remaining direct SQL is technical debt and should be migrated in bounded PRs. No schema/table/column was removed.

## FRONTEND DISPERSION

Canonical user entrypoint: `miniapp/index.html`.  
Canonical admin entrypoint: `miniapp/admin.html`.

The asset graph is layered and versioned. Cleanup is deferred until every candidate is proven unreachable from HTML/JS and covered by preview regression checks.

## TELEGRAM DISPERSION

Canonical Telegram process: `run.py -> app.main.main`.

`app/main.py` remains a large legacy core with mixed responsibilities, but it is the active source and cannot be split safely based on size alone.

## SIGNAL LIFECYCLE DISPERSION

The lifecycle crosses `app/main.py`, `app/db.py`, AutoTrade API/service and MT5 events. This is distributed by responsibility, but persistent identity mapping and Telegram reply anchors are the critical integration contract.

Known open PRs include work touching final result delivery and canonical signal/quote behavior; consolidation must not silently supersede those branches.

## EXECUTION DISPERSION

Execution authority remains `app/autotrade/api.py` + `app/autotrade/service.py` + persisted DB state. No trading strategy, risk, TP/SL, trailing or decision semantics were changed in this consolidation branch.

## DEPLOYMENT DISPERSION

Frontend deployment and VPS runtime are separate by design. Repository evidence does not currently contain the production Caddy/Nginx configuration, so reverse-proxy state remains **NOT VERIFIED** from this repository alone.

## TEST DISPERSION

GitHub Actions define targeted suites rather than one single full-test workflow. Canonical commands are recorded in `TESTING.md`.

No npm test/build contract exists because the audited repository has no `package.json`. No lint/type command is claimed because no `pyproject.toml`-based tool configuration was present.

## CANONICAL ARCHITECTURE AFTER CLEANUP

See:

- `ARCHITECTURE.md`
- `CONFIGURATION.md`
- `DEPLOYMENT.md`
- `TESTING.md`

## CHANGES IMPLEMENTED

1. Added canonical architecture contract.
2. Added canonical configuration contract.
3. Added canonical deployment contract.
4. Added canonical testing/verification contract.
5. Updated README to point to current Sources-of-Truth.
6. Consolidated duplicate PR templates into one canonical template.
7. Completed DATA-ACCESS-CONSOLIDATION-001 for four behavior-equivalent duplicate queries.
8. Added focused data-access regression coverage and wired it into Mini App CI.

## FILES MODIFIED

- `README.md`
- `.github/pull_request_template.md`
- `app/miniapp_api.py`
- `app/miniapp_admin_api.py`
- `.github/workflows/miniapp-ci.yml`

## FILES REMOVED

- `.github/PULL_REQUEST_TEMPLATE.md` — verified governance duplicate.

## FILES ADDED

- `ARCHITECTURE.md`
- `CONFIGURATION.md`
- `DEPLOYMENT.md`
- `TESTING.md`
- `REPOSITORY_CONSOLIDATION_REPORT.md`
- `DATA_ACCESS_CONSOLIDATION_001.md`
- `tests/test_data_access_consolidation.py`

## TEST RESULTS

At report creation time:

- Source inspection: PASS for documented architecture findings.
- Local Python compile: NOT VERIFIED in connector-only environment.
- Local pytest suites: NOT VERIFIED in connector-only environment.
- GitHub Actions: pending PR execution.
- Production E2E: NOT VERIFIED.
- MT5 compile/deploy/hash verification: NOT APPLICABLE to this docs/governance-only diff; production state still NOT VERIFIED.

## REGRESSION CHECK

This branch now contains bounded data-access refactors in Mini App/Admin API callers. The changes replace behavior-equivalent inline SQL with existing `app.db` helpers only; behavioral PASS is still based on executable regression/CI evidence rather than assumption.

Telegram receive/actions, signal creation/persistence/publication, Mini App loading, admin loading, lifecycle events, MT5 handoff, position events, close/result replies, initData and production API paths: **NOT VERIFIED at runtime by this audit environment**.

## SECURITY CHECK

- No secrets intentionally added.
- No `.env` or DB/runtime artifact added.
- New docs explicitly prohibit exposing credentials.
- Repository CI includes forbidden-runtime-file checks.

Full external secret scanning of historical Git objects: **NOT VERIFIED**.

## NOT VERIFIED

- Production Caddy/Nginx config and active service state.
- VPS filesystem/deployment hash.
- Telegram authenticated E2E.
- MT5 deployed EX5 identity.
- Full local pytest suite.
- Complete reverse-reference graph for every historical/versioned frontend asset.
- Historical Git use for every legacy script.

## OPEN RISKS

1. Large `app/main.py` legacy core remains a maintenance concentration risk.
2. Direct SQL outside `app/db.py` remains a consistency risk.
3. Open PRs touching signal contract, close delivery and market quotes may overlap future consolidation work.
4. Production reverse-proxy configuration is not repository-controlled.
5. Versioned frontend assets require a dedicated dependency/reachability audit before deletion.

## GIT STATUS

Branch: `refactor/repository-consolidation`  
Commits: documentation/governance consolidation commits  
Push: branch mutations are written directly to GitHub by the connected repository integration  
PR: to be created after this report commit  
CI: to be checked after PR creation

## REPOSITORY CLEANLINESS

**PARTIAL**

Canonical documentation, one verified governance duplicate, and four exact-equivalent API-layer SQL duplications are consolidated. Higher-risk SQL/runtime/frontend cleanup remains intentionally deferred.

## FINAL DECISION

**NOT READY** for declaring the entire repository fully consolidated.

The current branch is suitable for review as a bounded consolidation baseline. DATA-ACCESS-CONSOLIDATION-001 migrated only exact-equivalent duplicates; remaining direct SQL stays deferred where query semantics differ. Future work should continue query-by-query with focused regression evidence.

## NEXT COMMAND

After this PR is reviewed/green, the next bounded task should be:

```text
DATA-ACCESS-CONSOLIDATION-001:
Inventory every direct SQL statement outside app/db.py, map callers/tests and migrate only duplicated queries behind app/db.py repository functions without changing schema, signal semantics or execution behavior.
```


## DATA-ACCESS-CONSOLIDATION-002

Status: implemented on the consolidation branch.

Priority direct SQL was moved behind new exact-contract helpers in `app/db.py`:

- payment receipt idempotency -> `find_invoice_payment`
- Mini App execution history -> `miniapp_execution_history`
- Admin MT5 account resolution -> `latest_admin_mt5_account`
- Admin heartbeat row -> `admin_mt5_heartbeat`
- Admin signal live row -> `mt5_latest_managed_signal_state`
- Admin active managed live rows -> `mt5_managed_active_state`

Regression coverage locks filtering, projection, ordering, configured fallback, role filtering, case-insensitive signal matching and managed OPEN/PENDING semantics. No schema or signal/execution semantics changed.

Remaining direct SQL is deferred where equivalence has not yet been demonstrated.
