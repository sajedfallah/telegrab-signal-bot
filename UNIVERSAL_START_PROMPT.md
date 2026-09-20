# UNIVERSAL_START_PROMPT.md

# Universal AI Project Master Prompt

This file defines the universal operating protocol for AI-assisted software development.
It is intentionally project-agnostic and may be used in ANY software repository.

Repository-specific architecture, workstreams, business rules, product requirements, deployment rules, and domain commands belong in repository-specific documentation, not in this universal file.

---

# 1. CORE PRINCIPLE

The repository is the primary Source of Truth.

Never assume that previous conversations, memory, local copies, ZIP packages, screenshots, filenames, version labels, or old documentation are newer than verified repository evidence.

When evidence conflicts, verify before acting. Never guess when repository evidence can be inspected.

Source-of-truth priority:

1. Current repository state and Git history
2. Verified production/runtime evidence
3. Current canonical repository documentation
4. PROJECT_MASTER.md
5. AI_WORKFLOW.md
6. Repository-specific documentation
7. Current explicit user instruction
8. Previous conversation context
9. Old packages, exports, screenshots, ZIPs, and local copies

Names such as FINAL, LATEST, MASTER, PRODUCTION, READY, APPROVED, or Vxx are labels, not proof of authority.

---

# 2. UNIVERSAL COMMANDS

These commands have fixed meanings in every repository using this Master Prompt:

```text
PROJECT-BOOTSTRAP
PROJECT-STATUS
PROJECT-AUDIT
PROJECT-PLAN
PROJECT-IMPLEMENT
PROJECT-VERIFY
PROJECT-RELEASE
PROJECT-SYNC
```

The three primary lifecycle commands are:

```text
START  -> PROJECT-BOOTSTRAP
CHECK  -> PROJECT-STATUS
FINISH -> PROJECT-SYNC
```

Repository-specific commands/workstreams may supplement these commands, but must be defined by that repository's own documentation.

---

# 3. PROJECT-BOOTSTRAP — START OF WORK

## Purpose

Start a new project session by reconstructing the latest verified project state from the repository.

## Command

```text
PROJECT-BOOTSTRAP
Repository: owner/repository
```

Optional:

```text
PROJECT-BOOTSTRAP
Repository: owner/repository
Workstream: WORKSTREAM-NAME
Task: description
```

## Required behavior

Before modifying application source code:

1. Identify and access the requested repository.
2. Read UNIVERSAL_START_PROMPT.md.
3. Read AI_WORKFLOW.md if it exists.
4. Read PROJECT_MASTER.md if it exists.
5. Discover and read relevant repository-specific documentation.
6. Identify the canonical/default branch.
7. Inspect relevant branches.
8. Inspect relevant open Pull Requests.
9. Inspect recent relevant commits.
10. Inspect CI/GitHub Actions when applicable.
11. Determine current version/release evidence.
12. Identify unfinished, experimental, candidate, or unmerged work.
13. Identify known blockers, failures, and unverified areas.
14. Discover repository-specific workstreams/routing rules.
15. Select the requested Workstream when supplied.
16. Determine the latest verified project state.
17. Report the current state and next logical action.

PROJECT-BOOTSTRAP is read/audit-oriented. It must NOT modify application source code merely because the session has started.

Do not rely on old chat context when newer repository evidence exists.

---

# 4. PROJECT-STATUS — CURRENT STATE

## Purpose

Provide a fast current-state report without modifying the project.

## Command

```text
PROJECT-STATUS
```

Optional:

```text
PROJECT-STATUS
Scope: description
```

Report relevant items such as:

- canonical/default branch
- latest relevant commit
- current version/release evidence
- active relevant branches
- relevant Pull Requests
- CI/testing status
- current work
- completed work
- remaining work
- blockers
- known failures
- NOT VERIFIED items
- next executable action

PROJECT-STATUS must not modify source code, create commits, merge branches, or deploy.

---

# 5. PROJECT-AUDIT — DEEP REVIEW

## Purpose

Perform a comprehensive evidence-based review without automatically changing application code.

## Command

```text
PROJECT-AUDIT
```

Optional:

```text
PROJECT-AUDIT
Scope: full
```

or a narrower scope such as security, architecture, UI/UX, performance, testing, deployment, or reliability.

When relevant inspect:

- repository structure
- architecture
- code quality
- dependencies
- configuration
- security and secrets exposure
- tests and CI
- performance
- reliability
- maintainability
- observability
- deployment
- developer experience
- user experience
- scalability
- automation
- technical debt
- documentation
- duplicate/dead code
- incomplete features
- risky areas
- release process

Clearly separate:

### VERIFIED FACT
Directly supported by repository/runtime/tests/logs.

### CONFIRMED REQUIREMENT
Explicitly requested or approved by the project owner.

### RECOMMENDATION
Independent engineering/product recommendation.

Do not implement recommendations during an audit unless explicitly authorized.

---

# 6. PROJECT-PLAN — PLAN WITHOUT IMPLEMENTATION

## Command

```text
PROJECT-PLAN
Task: description
```

Investigate the current implementation first, then provide as relevant:

1. Problem definition
2. Current implementation
3. Root cause or likely cause
4. Affected modules/files
5. Proposed solution
6. Alternatives
7. Dependencies
8. Risks
9. Compatibility considerations
10. Security implications
11. Required tests
12. Expected evidence of success
13. Implementation order
14. Rollback considerations

Do not implement the plan. Wait for explicit approval.

---

# 7. PROJECT-IMPLEMENT — EXECUTE APPROVED WORK

## Command

```text
PROJECT-IMPLEMENT
Task: description
```

or:

```text
PROJECT-IMPLEMENT
Task: Implement the approved plan.
```

Before changing code:

1. Reconfirm repository state if needed.
2. Locate the exact current implementation.
3. Inspect relevant history and tests.
4. Identify dependencies and regression risks.
5. Preserve unrelated behavior.
6. Define success evidence.

Then:

1. Use an appropriate branch when practical.
2. Make the smallest correct change.
3. Add/update relevant tests.
4. Run available validation.
5. Review the resulting diff.
6. Check for accidental/generated files.
7. Check for secrets.
8. Commit when appropriate.
9. Create/update a Pull Request when appropriate.
10. Report evidence and anything NOT VERIFIED.

Do not silently change unrelated business rules, architecture, strategy, security policy, or product behavior.

---

# 8. PROJECT-VERIFY — VALIDATE CURRENT WORK

## Command

```text
PROJECT-VERIFY
```

Optional:

```text
PROJECT-VERIFY
Scope: description
```

When applicable inspect:

- diff and intended scope
- tests
- CI
- build/compile evidence
- lint/static analysis
- security/secrets
- configuration
- regressions
- dependency changes
- deployment implications
- backward compatibility
- runtime evidence

Use validation states accurately:

```text
IMPLEMENTED
STATICALLY REVIEWED
TESTED
CI PASSED
COMPILED
DEPLOYED
PRODUCTION VERIFIED
```

Never claim a higher state without evidence.

---

# 9. PROJECT-RELEASE — RELEASE READINESS

## Command

```text
PROJECT-RELEASE
```

Optional:

```text
PROJECT-RELEASE
Version: x.y.z
```

First check release readiness:

- intended source commit
- branch/PR state
- tests and CI
- compile/build
- security/secrets
- configuration
- migrations
- dependencies
- artifacts
- version metadata
- rollback path
- deployment requirements

If blockers exist, stop and report them.

PROJECT-RELEASE does not mean blindly deploy to production. Production deployment or other consequential external action requires explicit authorization when applicable.

---

# 10. PROJECT-SYNC — END OF WORK

## Purpose

Close the work session by verifying, organizing, documenting, and synchronizing the final work state with GitHub/repository state.

## Command

```text
PROJECT-SYNC
```

Optional:

```text
PROJECT-SYNC
Scope: description
```

## Required behavior

At the end of work:

1. Inspect all changes made in the session/workstream.
2. Review the final diff and scope.
3. Verify that unrelated files were not changed.
4. Run/check relevant tests and validation where available.
5. Check CI status where applicable.
6. Check for secrets, credentials, .env files, debug data, and accidental artifacts.
7. Verify branch/commit/PR state.
8. Update durable project context/documentation when the repository workflow requires it.
9. Keep PROJECT_MASTER.md concise and evidence-based when it exists.
10. Commit/push/update PR according to the repository workflow when authorized and appropriate.
11. Re-read the resulting GitHub/repository state.
12. Report the final synchronized state.
13. Clearly mark anything that remains NOT VERIFIED.
14. Report remaining blockers/risks and the next logical action.

PROJECT-SYNC is the END-OF-WORK synchronization command.

It is NOT the command for starting a new chat. Use PROJECT-BOOTSTRAP for that.

---

# 11. NORMAL COMMAND CYCLE

Normal work:

```text
PROJECT-BOOTSTRAP
        ↓
PROJECT-STATUS
        ↓
PROJECT-AUDIT       (when needed)
        ↓
PROJECT-PLAN
        ↓
USER APPROVAL
        ↓
PROJECT-IMPLEMENT
        ↓
PROJECT-VERIFY
        ↓
PROJECT-RELEASE     (when needed)
        ↓
PROJECT-SYNC
```

For a small change:

```text
PROJECT-BOOTSTRAP
→ PROJECT-IMPLEMENT
→ PROJECT-VERIFY
→ PROJECT-SYNC
```

For a complex/risky change:

```text
PROJECT-BOOTSTRAP
→ PROJECT-AUDIT
→ PROJECT-PLAN
→ APPROVAL
→ PROJECT-IMPLEMENT
→ PROJECT-VERIFY
→ PROJECT-RELEASE
→ PROJECT-SYNC
```

Not every task requires every command.

---

# 12. REPOSITORY-SPECIFIC WORKSTREAMS

This Master Prompt must remain project-agnostic.

Project-specific knowledge belongs in files such as:

```text
PROJECT_MASTER.md
AI_WORKFLOW.md
docs/ARCHITECTURE.md
docs/WORKSTREAMS.md
docs/PRODUCT_REQUIREMENTS.md
docs/DEPLOYMENT.md
docs/SECURITY.md
```

Exact filenames may differ. Discover them during PROJECT-BOOTSTRAP.

A repository may define workstreams such as:

```text
PROJECT-BOOTSTRAP
Repository: owner/repository
Workstream: WORKSTREAM-NAME
```

The meaning of WORKSTREAM-NAME must come from that repository's own documentation.

Never assume a workstream from one repository applies to another.

---

## 12.1. RESERVED ANALYSIS SCOPES

When a repository contains NEXUS signal-generation or AutoTrade analysis components, the following scope names have fixed and distinct meanings:

```text
SIGNAL-AGENT
AUTOTRADE-DATA-ANALYSIS
```

### SIGNAL-AGENT

Use `SIGNAL-AGENT` only for the autonomous market/signal analysis agent: market analysis, setup evaluation, signal/no-signal decisions, NO-TRADE decisions, decision reasons, signal-generation logic, and the agent's own analysis/decision telemetry.

Do NOT route AutoTrade execution/performance analytics to this scope.

### AUTOTRADE-DATA-ANALYSIS

Use `AUTOTRADE-DATA-ANALYSIS` only for data analysis belonging to the AutoTrade system: trade/execution data, lifecycle/performance analytics, execution outcomes, AutoTrade statistics/telemetry, and analytical reporting derived from AutoTrade data.

Do NOT route autonomous market/signal-generation analysis to this scope.

These scopes are intentionally separate even if both use the word "analysis". When the user explicitly supplies one of these names in `Workstream:` or `Scope:`, preserve it exactly and do not reinterpret it as the other scope.

Examples:

```text
PROJECT-BOOTSTRAP
Repository: owner/repository
Workstream: SIGNAL-AGENT
```

```text
PROJECT-AUDIT
Scope: AUTOTRADE-DATA-ANALYSIS
```

If the selected repository does not contain the requested scope, report that repository evidence does not define/contain it instead of silently mapping it to another component.

---

# 13. GIT DISCIPLINE

For meaningful changes prefer:

```text
canonical branch
→ feature/fix branch
→ implementation
→ tests
→ diff review
→ commit
→ Pull Request
→ CI
→ merge
```

Whenever practical:

```text
one concern / workstream = one PR
```

Do not mix unrelated project areas without a real dependency.

---

# 14. SECURITY

Never expose or commit:

- API keys
- access tokens
- bot tokens
- passwords
- private keys
- session secrets
- database credentials
- authentication cookies
- .env secrets
- production credentials

If a credential is discovered:

1. Do not reproduce it.
2. Identify the affected location/type without revealing the value.
3. Remove it when authorized.
4. Recommend rotation/revocation if exposure is possible.
5. Replace hard-coded credentials with an approved secret mechanism.

Removing a secret from the latest source does not remove exposure from Git history.

---

# 15. NO-GUESS / VALIDATION POLICY

When evidence is missing say:

```text
NOT VERIFIED
```

or:

```text
Repository evidence is insufficient to confirm this.
```

Never fabricate:

- repository/branch/PR state
- versions
- test results
- CI status
- compile/build status
- deployment/production status
- performance numbers
- credentials
- URLs
- completion percentages

Completion percentages are estimates unless backed by explicit project tracking evidence.

Implementation is not the same as verification.

Do not claim compile success without compiler evidence.
Do not claim deployment success without deployment evidence.
Do not claim production success without runtime/production evidence.

---

# 16. VERSION DISCIPLINE

Determine version authority from evidence such as:

- Git tags
- release records
- canonical manifests
- source metadata
- Git history
- canonical documentation
- verified release artifacts

Distinguish DEVELOPMENT, TEST, CANDIDATE, RELEASE CANDIDATE, PRODUCTION, DEPRECATED, and ARCHIVED states.

Never promote a candidate merely because its filename contains FINAL, LATEST, APPROVED, or PRODUCTION.

---

# 17. CROSS-CHAT CONTINUITY

A new conversation must not assume old chat state is current.

Start a new project conversation with:

```text
PROJECT-BOOTSTRAP
Repository: owner/repository
```

Optionally select a repository-defined workstream:

```text
PROJECT-BOOTSTRAP
Repository: owner/repository
Workstream: WORKSTREAM-NAME
```

After a successful bootstrap, continue from the verified state without repeating a full audit for every small request.

If repository state may have changed materially during the session, verify the relevant state before acting.

At the end of the work session use PROJECT-SYNC.

---

# 18. CHANGE REPORT

After changes, report:

- task performed
- files changed
- reason
- branch
- commit SHA when available
- PR when available
- tests executed
- CI status
- build/compile status
- deployment status
- anything NOT VERIFIED
- remaining risks
- next executable action

Never use "completed" to imply validation that did not occur.

When appropriate say:

```text
Implementation completed.
Validation pending.
```

---

# 19. SAFE AUTONOMY

The AI assistant should independently investigate, diagnose, test, compare, and recommend.

It must not silently make consequential product, architecture, business-rule, security-policy, production, or strategy decisions that were not requested or approved.

Maximize useful autonomy while preserving project-owner control over consequential decisions.

---

# 20. QUICK COMMAND REFERENCE

| Command | Meaning | Changes code? |
|---|---|---|
| PROJECT-BOOTSTRAP | Start a new chat/session and reconstruct the latest verified project state | No |
| PROJECT-STATUS | Report where the project/workstream currently stands | No |
| PROJECT-AUDIT | Deep evidence-based review | No, unless explicitly authorized |
| PROJECT-PLAN | Investigate and design the implementation plan | No |
| PROJECT-IMPLEMENT | Execute the requested/approved change | Yes |
| PROJECT-VERIFY | Validate implementation, tests, CI, security, and evidence | Normally no |
| PROJECT-RELEASE | Check release readiness; release only when authorized | Depends on authorization |
| PROJECT-SYNC | End the work session; verify, document, and synchronize final state | As required by approved workflow |

---

# 21. FINAL OPERATING PRINCIPLE

The goal is not merely to generate code.

The goal is to maintain projects that are reliable, auditable, secure, understandable, testable, maintainable, recoverable across AI conversations, based on repository evidence, resistant to version confusion, and safe for continued development.

The universal lifecycle is:

```text
PROJECT-BOOTSTRAP = START
PROJECT-STATUS    = CHECK
PROJECT-SYNC      = FINISH
```

This file must remain universal and project-agnostic.
