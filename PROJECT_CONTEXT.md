# NEXUS — PROJECT_CONTEXT.md

> **Purpose:** Persistent AI project context, repository operating contract, and handoff document.
>
> **Repository:** `sajedfallah/telegrab-signal-bot`  
> **Canonical branch:** `main`  
> **GitHub is the source of truth for tracked project state.**  
> **Last context sync:** 2026-09-20

---

## 0. AI START HERE — MANDATORY

This file is a living control document for any AI/developer working on NEXUS.

Do **not** treat this file, chat history, filenames, local folders, ZIP names, or version labels as sufficient proof of the current state.

Before making changes, reconcile this document with the **actual repository state**:
- repository metadata and default branch;
- current `main` HEAD;
- active/open PRs and relevant branches;
- recent commits;
- version/release documentation;
- deployment documentation/status when relevant;
- current task-specific files and tests.

If this document conflicts with verified Git state, **Git wins**. Correct this document during the next safe sync.

Never infer that a file/branch is newest merely because its name contains `FINAL`, `LATEST`, `NEW`, `TEST`, or a larger-looking version number.

---

# 1. STANDARD AI COMMANDS

## PROJECT-BOOTSTRAP

When the user says **`PROJECT-BOOTSTRAP`**, perform a read-first project bootstrap.

Mandatory sequence:
1. Read this entire file.
2. Inspect the repository and verify the canonical/default branch.
3. Inspect `main` HEAD and recent commits.
4. Inspect active branches and open PRs relevant to the current work.
5. Read `README.md`, `CONTRIBUTING.md`, `VERSION.txt`, and relevant docs.
6. Determine the latest **verified** stable state and the latest active/test state. Do not guess from names.
7. Identify the current task, unfinished work, known blockers, and next logical action.
8. Check deployment state when the task affects deployment.
9. Report discrepancies between this file and Git before editing code.
10. Continue from the verified latest state; never restart from an obsolete branch/package.

Expected short output:
- Canonical branch / HEAD
- Relevant active branch or PR
- Production state
- Current task
- Last completed work
- Open/blocking items
- Next action
- Context drift, if any

**BOOTSTRAP is read/reconcile first. It must not silently rewrite production or merge branches.**

---

## PROJECT-STATUS

When the user says **`PROJECT-STATUS`**, inspect and report status without intentionally changing the repository.

Report:
- repository and canonical branch;
- current `main` HEAD;
- relevant active branches/PRs;
- verified production/deployment identity where applicable;
- current stable/test version(s) by subsystem;
- current task and completion state;
- blockers/known issues;
- whether docs/context appear synchronized;
- recommended next action.

**PROJECT-STATUS is read-only.**

---

## PROJECT-SYNC

When the user says **`PROJECT-SYNC`**, reconcile the completed work with GitHub and leave the project in a clean, understandable state.

Mandatory sequence:
1. Re-run the relevant parts of `PROJECT-BOOTSTRAP`.
2. Review all work completed in the current session.
3. Inspect diffs before writing/committing.
4. Run relevant validation/tests.
5. Remove accidental temporary/generated clutter when safe.
6. Update canonical docs affected by the change.
7. Update this `PROJECT_CONTEXT.md`.
8. Ensure secrets/credentials/runtime data are not being committed.
9. Commit with a clear, scoped message.
10. Push to the correct short-lived branch or approved target.
11. Use PR/Preview workflow where required; do not bypass repository governance.
12. Verify the remote state after the write.
13. If merged/deployed, verify the resulting canonical state.
14. Record unresolved work under **Current Task / Known Issues / Next Actions**.

A sync is not complete merely because code was edited. It is complete only when the repository state, documentation, tests, and handoff context agree.

---

# 2. SOURCE-OF-TRUTH HIERARCHY

Use this order when evidence conflicts:

1. Actual GitHub repository state and commit history.
2. Verified production/runtime/deployment state for runtime facts.
3. Canonical repository documentation on current `main`.
4. This `PROJECT_CONTEXT.md`.
5. Current chat/task instructions.
6. Historical chat summaries, old packages, old branches, backups, filenames.

Important distinction:
- **GitHub `main`** is the canonical tracked source.
- **VPS/runtime state** can be authoritative for facts that only exist at runtime.
- Never reset a production runtime merely to make it resemble Git history.
- A runtime difference must be investigated and deliberately reconciled.

---

# 3. PROJECT IDENTITY

**Project:** NEXUS  
**Repository:** `sajedfallah/telegrab-signal-bot`  
**Default/production branch:** `main`  
**Repository model:** Trunk-Based Development with short-lived branches.

NEXUS currently contains multiple related subsystems, including:
- Telegram bot;
- Mini App;
- subscription/payment flows;
- AutoTrade;
- MT5 components;
- signal lifecycle and reporting;
- analysis/ICT tooling;
- content/academy modules;
- supporting APIs;
- admin/control surfaces.

Do not assume all subsystems share the same product version number. For example, repository application versioning and NEXUS ICT Expert versioning can advance independently.

---

# 4. VERIFIED CANONICAL DEPLOYMENT MAP

At the last context sync:

| Area | Canonical state |
| --- | --- |
| GitHub | `sajedfallah/telegrab-signal-bot` |
| Production branch | `main` |
| Mini App hosting | Vercel |
| Vercel project | `telegrab-signal-bot` |
| Vercel root | `miniapp` |
| Mini App production | `https://telegrab-signal-bot.vercel.app/` |
| VPS/API | `https://api.nexustrade.ir` |
| Mini App API proxy | `/miniapp/api/*` -> VPS API |
| Telegram Main Mini App | canonical Vercel production URL |
| Backend / AutoTrade / MT5 | Windows VPS; not Vercel |
| Live Charts market truth | NEXUS/MT5 feed via VPS API |

Before relying on deployment details, re-check `README.md` and `docs/DEPLOYMENT_BRANCHING.md`.

Do not store ephemeral Vercel deployment IDs here as permanent production identity.

---

# 5. REPOSITORY MAP

Key paths currently include:

| Path | Responsibility |
| --- | --- |
| `app/` | Python application/backend modules |
| `app/autotrade/` | AutoTrade/exchange/execution-related backend |
| `app/content/` | content/agent/editorial modules |
| `miniapp/` | Telegram Mini App frontend and Vercel configuration |
| `mt5/` | MT5-related tracked components |
| `tests/` | automated tests |
| `scripts/` | project scripts/automation |
| `tools/` | project tooling |
| `docs/` | canonical project/deployment documentation |
| `docs/nexus-ict/` | NEXUS ICT Expert handoff/test/roadmap docs |
| `.github/workflows/` | CI/governance automation |
| `VERSION.txt` | repository/application version marker; not proof of every subsystem version |
| `README.md` | high-level canonical repository/deployment overview |

Before modifying an unfamiliar subsystem, inspect its actual current tree and nearby documentation.

---

# 6. BRANCH POLICY

Canonical policy:
- `main` = canonical production/tracked state.
- New work starts from current `main`.
- Use short-lived branches.
- Merge through PR where repository policy requires review/CI/Preview.
- Delete merged branches after safe verification when no dependency remains.

Approved prefixes:
- `feature/`
- `bugfix/`
- `hotfix/`
- `release/` for temporary coordinated release candidates only
- `docs/`
- `ops/`

Historical, backup, integration, old release, and superseded feature branches are **not** valid development baselines merely because they exist.

Never merge unrelated branches solely to reduce branch count.

For NEXUS ICT Expert, follow `docs/nexus-ict/DEVELOPMENT_HANDOFF_FA.md`.

---

# 7. CURRENT VERIFIED STATUS SNAPSHOT

This section is a **snapshot**, not a substitute for BOOTSTRAP.

At the time this file was introduced:
- repository default branch is `main`;
- `main` was verified as the canonical branch;
- the latest verified `main` commit before creation of this context file was `fa8a582588fa1961619c879998cce6b47787e1a1`;
- that commit canonicalized the NEXUS ICT V22.46 forward-test handoff;
- `VERSION.txt` on `main` reports `0.6.5`, which is a repository/application version marker and must not be confused with the ICT Expert V22.x lineage;
- Mini App production identity is the stable Vercel production domain;
- backend/AutoTrade/MT5 runtime remains on the VPS.

Because this file itself creates a newer commit, **never use the SHA above as “current HEAD” without checking GitHub.**

---

# 8. CURRENT NEXUS ICT TEST STATE

Canonical ICT handoff docs:
- `docs/nexus-ict/DEVELOPMENT_HANDOFF_FA.md`
- `docs/nexus-ict/ONE_WEEK_FORWARD_TEST_V22_46_FA.md`
- relevant current-status/roadmap files under `docs/nexus-ict/`

Verified test policy at context creation:
- V22.46 is in a one-week Demo Forward Test window, documented as 2026-09-18 through 2026-09-25.
- During the freeze, strategy-rule changes are prohibited.
- Allowed work is limited to bug/data-integrity/performance/Telegram/UI fixes described in the test plan.
- Test evidence and dataset integrity must be collected before proposing V22.47 strategy changes.

Any newer branch/version must be verified against Git history, docs, PRs, and test evidence before declaring it the new canonical version.

---

# 9. CURRENT TASK

**Primary persistent task:** keep NEXUS GitHub, project context, and active development state synchronized so work can continue across different AI chats without repeated manual explanation.

For each work session, replace/update the task block below during `PROJECT-SYNC`:

- **Active task:** Reconcile the live Telegram AutoTrade signal-publication format with GitHub.
- **Relevant subsystem:** Telegram Bot / AutoTrade / MT5 signal publication.
- **Working branch/PR:** `hotfix/autotrade-persian-text-signal-20260920` / PR to `main`.
- **Last completed step:** Replaced image/card publication with text-only Telegram posts and standardized the root signal caption as the approved Persian format.
- **Validation evidence:** Live VPS formatter produced the expected Persian HTML output; `app/main.py` passed `python -m py_compile`; both `NEXUS-AutoTrade-API` and `NEXUS-Telegram-Bot` were restarted and verified Running.
- **Blocker:** Final confirmation requires observing the next naturally generated AutoTrade signal in Telegram.
- **Next action:** Verify the next real AutoTrade signal uses the new Persian text-only format, then continue lifecycle formatting for Partial Close / Final Result if requested.

Do not invent these fields when evidence is unavailable. Mark them `UNKNOWN — VERIFY`.

---

# 10. DECISION LOG — STABLE RULES

Keep only durable decisions here. Git history remains the detailed historical log.

1. GitHub is the canonical tracked source of truth.
2. `main` is the canonical production branch.
3. Work should use short-lived branches rather than accumulating permanent task branches.
4. Mini App frontend is hosted on Vercel; backend/AutoTrade/MT5 runtime stays on the VPS.
5. Production Mini App identity is the stable production domain, not an ephemeral deployment ID.
6. Broker/MT5 remains the authority for live market/trade truth; do not manufacture Gold/Forex candles.
7. Secrets never belong in source, docs, screenshots, issues, PR text, or this context file.
8. AI must verify repository state before claiming a version/branch/build is latest.
9. AI must not use `FINAL`, `LATEST`, `NEW`, `TEST`, ZIP names, or folder names as proof of recency.
10. `PROJECT-SYNC` must update this document after meaningful project-state changes.
11. Documentation must describe reality; do not update docs to hide an unresolved repository/runtime mismatch.

---

# 11. PROTECTED / HIGH-RISK AREAS

Do not make destructive or production-impacting changes without verifying scope and the user's intent.

High-risk areas include:
- production `main`;
- VPS services and production runtime;
- database/runtime state;
- Telegram Bot configuration;
- payment/subscription flows;
- AutoTrade execution;
- MT5 execution/position management;
- licenses/authentication;
- Vercel production configuration;
- API rewrites/routes;
- secrets and environment configuration.

Never:
- force-push production history without explicit justification/approval;
- delete a branch before verifying it is merged/superseded and not used as another PR's base;
- reset/clean the production VPS simply to match Git;
- expose credentials;
- deploy backend/MT5 runtime to Vercel;
- silently change trading strategy during an explicit forward-test freeze.

---

# 12. SECRETS POLICY

Never commit:
- Telegram Bot Tokens;
- API keys;
- broker credentials;
- MT5 credentials/secrets;
- payment secrets;
- database credentials;
- private signing/license secrets;
- `.env`;
- credential-bearing screenshots/logs;
- private MQ5 server artifacts containing runtime secrets.

Store only environment-variable **names** and safe configuration documentation in Git.

If a credential is exposed, treat it as compromised and rotate/revoke it through the appropriate service.

---

# 13. VALIDATION POLICY

Never report **DONE** only because files changed.

Validation must be proportional to the subsystem.

Repository baseline documented in `README.md` includes checks such as:
```bash
python -m compileall -q app run.py run_api.py
python -m pytest tests/test_miniapp_api.py -q
python -m pytest tests/test_agentic_content_mvp.py tests/test_free_signal_topic_routing.py tests/test_customer_experience.py -q
```

These are not universal substitutes for task-specific tests.

For Mini App changes, also verify:
- Vercel Preview when applicable;
- authenticated Telegram behavior when auth-sensitive;
- no regression to API proxy behavior;
- approved responsive/mobile layout.

For execution/MT5 changes, require relevant compile/runtime/demo evidence and lifecycle validation.

For docs-only changes, verify links, paths, branch names, and factual consistency against current Git.

---

# 14. DEFINITION OF DONE

A task is DONE only when applicable items are satisfied:

- requested implementation is complete;
- diff reviewed;
- relevant tests/validation pass;
- no accidental secrets;
- no unrelated changes;
- temporary artifacts cleaned;
- docs updated where behavior/state changed;
- `PROJECT_CONTEXT.md` updated when project state changed;
- changes committed with a clear message;
- changes pushed to the intended branch;
- PR/Preview/merge completed when required;
- remote state verified;
- production verified when deployment was part of the task;
- remaining issues and next action recorded.

If any required item is missing, report the task as **PARTIAL**, **BLOCKED**, or **READY FOR REVIEW**, not DONE.

---

# 15. ARTIFACT & CLEANUP POLICY

Prevent repository sprawl.

Do not create chains such as:
- `final`
- `final2`
- `final-new`
- `latest-final`
- arbitrary backup copies
- duplicate ZIPs
- unexplained version folders

unless the project deliberately requires a versioned artifact.

Prefer:
- Git history;
- tags/releases when appropriate;
- one canonical path;
- short-lived branches;
- explicit release artifacts.

Before deleting historical artifacts, verify whether they are intentionally retained for release/audit/rollback.

---

# 16. KNOWN ISSUES / TECHNICAL DEBT

At context creation:
- repository contains many historical branches; cleanup must remain audited and non-destructive;
- branch protection/rules should be verified in GitHub settings rather than assumed;
- multiple subsystem version lineages exist and can be confused if version labels are treated globally;
- ICT V22.46 forward-test evidence is still governed by the one-week test plan until its documented review is complete.

Update this section during `PROJECT-SYNC`; remove items only after verified resolution.

---

# 17. NEXT ACTIONS

Default priority when entering a new chat:
1. Run `PROJECT-BOOTSTRAP`.
2. Verify whether there is a newer active/test branch, PR, commit, or deployment than this snapshot.
3. Resume the user's current task from that verified state.
4. Preserve the current forward-test/release constraints.
5. At the end of meaningful work, run `PROJECT-SYNC`.

---

# 18. CHANGE LOG FOR THIS CONTEXT FILE

Keep this short. Detailed history belongs in Git.

- **2026-09-19:** Created `PROJECT_CONTEXT.md` as the persistent AI bootstrap/status/sync contract for NEXUS. Added source-of-truth hierarchy, repository/deployment map, branch policy, safety rules, validation/DoD, cleanup policy, ICT forward-test context, and the three standard commands.
- **2026-09-20:** Synced Telegram AutoTrade signal publication with the live VPS behavior: Persian text-only signal cards, no chart/image publication, and current runtime validation/restart evidence recorded.

---

# 19. FINAL AI RULE

The goal is **continuity without drift**.

At the start of work: **verify reality**.  
During work: **change only the intended scope**.  
At the end: **test, document, clean, commit, push, verify, and hand off**.

Never allow chat history, stale context, old branches, duplicate packages, or misleading filenames to become a second source of truth.
