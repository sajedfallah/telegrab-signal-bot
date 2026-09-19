# UNIVERSAL_START_PROMPT.md

# Universal Project Master Prompt

This file defines the standard startup, synchronization, audit, and development workflow for projects managed with AI assistants such as ChatGPT or Codex.

The repository is the primary Source of Truth.

Do not rely on old conversations, filenames, local packages, remembered version numbers, or previous assumptions when repository evidence is available.

---

# 1. MASTER START COMMAND

The universal project entry command is:

```text
PROJECT-SYNC
Repository: owner/repository
```

Example:

```text
PROJECT-SYNC
Repository: sajedfallah/example-project
```

`PROJECT-SYNC` is the single universal synchronization command.

Do not introduce alternative project-start commands unless the repository explicitly defines them.

---

# 2. PROJECT-SYNC BEHAVIOR

When a new conversation starts with `PROJECT-SYNC`, first synchronize your understanding with the repository.

Before modifying application source code:

1. Identify the requested repository.
2. Treat the specified repository as the primary Source of Truth.
3. Read `UNIVERSAL_START_PROMPT.md`.
4. Read `AI_WORKFLOW.md` if it exists.
5. Read `PROJECT_MASTER.md` if it exists.
6. Read repository-specific architecture, workflow, routing, or project-context documentation if it exists.
7. Inspect the current repository state.
8. Identify the default/canonical branch.
9. Inspect relevant active branches.
10. Inspect relevant open Pull Requests.
11. Inspect recent commits related to the requested work.
12. Inspect CI / GitHub Actions status when applicable.
13. Identify the latest verified implementation state.
14. Identify unfinished, experimental, candidate, or unmerged work.
15. Identify known blockers, risks, and unresolved failures.
16. Determine which project area or workstream the user's request belongs to.

Do not modify application source code until enough repository evidence has been gathered to understand the current state and the requested scope.

Documentation-only synchronization may be performed when explicitly requested.

---

# 3. SOURCE-OF-TRUTH HIERARCHY

When information conflicts, use this priority order:

1. Current repository state and Git history
2. Verified production/runtime state
3. Current canonical documentation on the repository's canonical branch
4. `PROJECT_MASTER.md`
5. `AI_WORKFLOW.md`
6. Repository-specific context/routing documentation
7. Current user instruction
8. Previous conversation context
9. Old packages, exports, ZIP files, local copies, screenshots, or filenames

A filename is not proof of version authority.

Names such as:

```text
FINAL
LATEST
NEW
MASTER
PRODUCTION
READY
V1
V2
V35
V99
```

must never be treated as proof that a file is the latest or canonical version.

Verify using repository evidence.

---

# 4. REQUIRED INITIAL AUDIT

If `AI_WORKFLOW.md` defines a repository audit, follow it completely.

If no repository-specific audit exists, perform a reasonable audit covering:

- repository structure
- architecture
- active development state
- important branches
- Pull Requests
- recent relevant commits
- CI status
- application entry points
- configuration
- dependencies
- security-sensitive configuration
- tests
- deployment configuration
- documentation
- known unfinished work
- obvious dead/duplicate code
- current release/version evidence

During the audit:

- do not guess
- do not silently fill missing information
- distinguish facts from assumptions
- distinguish verified implementation from planned functionality
- distinguish repository state from production state

---

# 5. FACT / REQUIREMENT / RECOMMENDATION SEPARATION

Always distinguish between:

## VERIFIED FACT

Directly supported by repository, runtime, CI, logs, tests, or other reliable evidence.

## CONFIRMED REQUIREMENT

Explicitly requested or approved by the user/project owner.

## RECOMMENDATION

Your own engineering, product, architecture, security, UX, or development recommendation.

Never present a recommendation as if it already exists.

Never implement a recommendation solely because you recommended it.

Obtain explicit approval when the recommendation materially changes behavior, architecture, strategy, user experience, risk, or production logic.

---

# 6. DEVELOPMENT RULES

Before making changes:

1. Identify the exact problem.
2. Identify the affected workstream/module.
3. Locate the current implementation.
4. Inspect related tests.
5. Inspect relevant recent history.
6. Determine dependencies and side effects.
7. Preserve unrelated behavior.
8. Define expected evidence for success.

Prefer the smallest correct change.

Do not perform broad refactors while fixing an isolated issue unless required.

Do not silently change business rules, trading strategy, risk policy, execution rules, pricing rules, permissions, security rules, or user-facing behavior.

If such a change appears necessary, explain it before implementation.

---

# 7. GIT WORKFLOW

GitHub/repository state is authoritative.

For meaningful or risky changes, prefer:

```text
canonical branch
    ↓
feature/fix branch
    ↓
implementation
    ↓
tests
    ↓
review/diff
    ↓
Pull Request
    ↓
CI
    ↓
merge
```

Avoid mixing unrelated changes in one Pull Request.

Whenever practical:

**one concern / workstream = one PR**

Before merging, verify:

- intended files only
- no accidental generated files
- no secrets
- no `.env`
- no unrelated code
- no debug credentials
- no stale packages
- no unexpected architecture changes
- relevant tests
- CI status

---

# 8. SECURITY RULES

Never expose or commit:

- API keys
- bot tokens
- access tokens
- passwords
- private keys
- session secrets
- database credentials
- authentication cookies
- production credentials
- `.env` secrets

If a credential is found in repository history or source code:

1. Do not reproduce it in chat.
2. Report the location/type without revealing the secret.
3. Remove it from active source when authorized.
4. Recommend rotation/revocation if exposure is possible.
5. Use environment variables or an approved secret-management mechanism.

A secret removed from the latest commit may still be compromised if it exists in Git history.

---

# 9. TESTING AND VALIDATION

Never claim something works solely because the code looks correct.

Separate these states:

```text
IMPLEMENTED
STATICALLY REVIEWED
TESTED
CI PASSED
COMPILED
DEPLOYED
PRODUCTION VERIFIED
```

Only claim a state when evidence exists.

Examples:

Do not say:

```text
Compile successful
```

without compiler evidence.

Do not say:

```text
Deployment successful
```

without deployment evidence.

Do not say:

```text
Production fixed
```

without production/runtime evidence.

When evidence is unavailable, state exactly what remains unverified.

---

# 10. VERSION AND RELEASE DISCIPLINE

Never infer the current version from filenames alone.

Determine versions from appropriate evidence such as:

- Git tags
- release metadata
- canonical manifests
- source metadata
- canonical documentation
- commit history
- verified release artifacts

Clearly distinguish:

```text
development
candidate
test
release candidate
production
deprecated
archived
```

Do not mark a candidate as production without required validation.

---

# 11. PROJECT_MASTER.md

If `PROJECT_MASTER.md` exists, keep it aligned with verified project state when the repository workflow requires it.

It should contain concise, durable project knowledge such as:

- project purpose
- architecture
- current canonical version/state
- major completed features
- active work
- known blockers
- important technical decisions
- active branches/PRs when relevant
- deployment model
- testing status
- next major actions

Do not turn `PROJECT_MASTER.md` into an uncontrolled activity log.

Use Git history for detailed historical records.

---

# 12. INDEPENDENT ENGINEERING REVIEW

After understanding the project, independently identify evidence-based opportunities involving:

- architecture
- code quality
- security
- testing
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
- useful future features

Recommendations must be clearly marked as recommendations.

Do not automatically implement them.

---

# 13. PROJECT-SYNC RESPONSE

After a full synchronization/audit, provide a concise project status covering, when relevant:

1. Overall project state
2. Canonical branch/version
3. Rough completion estimate — clearly marked as an estimate
4. Completed features
5. Partially completed features
6. Missing or planned features
7. Broken/risky areas
8. Active relevant branches
9. Active relevant Pull Requests
10. CI/testing status
11. Security blockers
12. Top 5 next executable actions
13. Top 5 recommended improvements
14. Quick wins
15. Strategic long-term improvements
16. Optional future feature ideas
17. Whether there are blockers to continuing development safely

Do not manufacture items merely to fill this list.

If a category is not relevant, omit it.

---

# 14. CONTINUATION MODE

After `PROJECT-SYNC` has completed, do not repeat the full repository audit before every small request.

Continue from the verified repository state.

Re-synchronize when:

- the user explicitly sends `PROJECT-SYNC`
- another developer may have changed the repository
- a PR was merged
- a branch changed
- deployment occurred
- CI state changed materially
- repository state is uncertain
- significant time/context has passed
- the requested task depends on fresh repository state

---

# 15. CROSS-CHAT BEHAVIOR

A new AI conversation must not assume that previous chat context is current.

For a fresh conversation, the preferred startup format is:

```text
PROJECT-SYNC
Repository: owner/repository
```

The repository should provide enough durable documentation for the AI assistant to reconstruct the project state.

Old chat history may provide context, but it must not override newer repository evidence.

---

# 16. PROJECT-SPECIFIC ROUTING

A repository may define internal workstreams.

If it does, select the appropriate workstream before making changes.

Workstream boundaries should prevent unrelated systems from becoming coupled.

Cross-workstream changes are allowed only when a real dependency requires them.

When this happens:

1. identify the dependency
2. explain why multiple workstreams are affected
3. preserve interface boundaries
4. avoid unrelated changes
5. test the integration boundary

---

# 17. NEXUS ICT SPECIAL ROUTING

This section applies only when:

```text
Repository: sajedfallah/nexus-ict
```

After `PROJECT-SYNC`, one workstream command may be provided.

Available workstreams:

```text
NEXUS-BOT
NEXUS-DATA
NEXUS-SIGNAL
NEXUS-CORE
```

The assistant must read:

```text
docs/NEXUS_WORKSTREAMS.md
```

before modifying workstream-specific code.

---

## NEXUS-BOT

Scope:

- Signal Bot
- Telegram delivery
- signal publication
- lifecycle messaging
- final trade result
- reply relationships
- Telegram routing
- subscriptions where applicable
- delivery retries
- Telegram observability
- downstream presentation of already-created signals

The Bot does not independently perform ICT market analysis or invent trading signals.

Example:

```text
PROJECT-SYNC
Repository: sajedfallah/nexus-ict
NEXUS-BOT
```

---

## NEXUS-DATA

Scope:

- NEXUS ICT indicator
- Data Analyzer
- ICT analytical agents
- market/chart data interpretation
- multi-timeframe analysis
- HTF context
- FVG
- Order Blocks
- liquidity
- Premium/Discount
- Quadrant
- setup construction
- setup scoring
- entry validation
- execution diagnostics
- Trail07
- analytics
- analytical viewer
- indicator-related evidence and telemetry

Example:

```text
PROJECT-SYNC
Repository: sajedfallah/nexus-ict
NEXUS-DATA
```

---

## NEXUS-SIGNAL

Scope:

- autonomous market monitoring
- watchlist scanning
- session monitoring
- opportunity detection
- candidate generation
- autonomous signal evaluation
- signal qualification
- policy/risk gates before issuance
- final structured BUY / SELL / NO SIGNAL decision
- reason codes
- opportunity expiry
- transport-neutral signal output

`NO SIGNAL` is a valid and preferred result when evidence is insufficient.

The autonomous signal agent must not force trade frequency.

Example:

```text
PROJECT-SYNC
Repository: sajedfallah/nexus-ict
NEXUS-SIGNAL
```

---

## NEXUS-CORE

Scope only shared contracts and interfaces such as:

- signal schemas
- event schemas
- shared reason codes
- symbol/timeframe identifiers
- versioned interfaces
- shared protocol definitions

Do not turn `NEXUS-CORE` into a miscellaneous dumping ground.

Example:

```text
PROJECT-SYNC
Repository: sajedfallah/nexus-ict
NEXUS-CORE
```

---

# 18. NEXUS WORKSTREAM ISOLATION

For `sajedfallah/nexus-ict`:

Do not mix Bot presentation work with Data/Indicator/Execution work in the same change unless necessary.

Do not mix autonomous Signal Agent decision logic with Telegram presentation.

Do not move analytical responsibilities into the Bot.

Do not move Telegram-specific presentation into the autonomous Signal Agent.

Shared communication should use explicit versioned contracts whenever practical.

Preferred conceptual architecture:

```text
NEXUS-DATA
    ↓
structured analytical data

NEXUS-SIGNAL
    ↓
structured signal decision

NEXUS-BOT
    ↓
human-facing delivery

NEXUS-CORE
    ↕
shared contracts/interfaces
```

Not every signal must necessarily originate from `NEXUS-SIGNAL`; existing product flows may provide already-approved signals to downstream consumers.

Preserve existing behavior unless an approved migration changes it.

---

# 19. NEXUS CURRENT STRATEGY PROTECTION

When working on NEXUS trading systems, never silently modify established trading strategy or risk behavior while fixing infrastructure, latency, UI, Telegram, logging, or reliability issues.

Strategy changes must be treated separately from engineering fixes.

Examples include:

- timeframe logic
- ICT setup rules
- FVG interpretation
- Order Block rules
- Quadrant rules
- entry conditions
- stop-loss rules
- take-profit rules
- trailing behavior
- position sizing
- risk limits
- session filters
- signal scoring thresholds

If the requested engineering fix would change trading behavior, explicitly identify the change before implementation.

---

# 20. NEXUS SIGNAL OUTPUT CONTRACT

Where applicable, autonomous signal output should remain machine-readable and transport-neutral.

Typical fields may include:

```text
symbol
time
direction
entry
sl
targets
score
setup
reason_codes
expiry
source
```

Do not couple core signal decisions to Telegram-specific formatting.

---

# 21. NEXUS TELEGRAM PRESENTATION BOUNDARY

Telegram is a presentation/delivery layer.

Internal analytical, execution, and lifecycle telemetry should not automatically become user-facing Telegram messages.

User-facing messages should follow the currently approved product specification.

Internal events may remain available in:

- logs
- analytics
- telemetry
- admin tools
- diagnostics

without being sent to end users.

---

# 22. REPOSITORY RESTRUCTURING

Do not move production files merely to make the repository look cleaner.

Architecture migrations should be incremental.

Before moving files:

1. identify imports/dependencies
2. identify build/deployment references
3. identify CI references
4. identify runtime paths
5. identify documentation links
6. plan compatibility
7. migrate in controlled steps
8. verify after each stage

Repository organization is valuable, but production stability has priority.

---

# 23. NO-GUESS POLICY

When evidence is missing:

Say:

```text
Not verified
```

or:

```text
Repository evidence is insufficient to confirm this.
```

Do not fabricate:

- versions
- deployment status
- test results
- production state
- branch state
- PR state
- CI state
- runtime behavior
- performance numbers
- completion percentages
- credentials
- URLs
- configuration values

Completion percentages are estimates unless directly defined by project tracking data.

---

# 24. CHANGE REPORTING

After making repository changes, report:

- what changed
- why it changed
- files changed
- branch
- commit SHA when available
- PR when available
- tests executed
- CI status
- anything not verified
- remaining risks
- next recommended executable step

Do not say "done" if important validation is still pending.

Instead distinguish:

```text
Code change completed.
Validation pending.
```

when appropriate.

---

# 25. FINAL OPERATING PRINCIPLE

The objective is not merely to produce code.

The objective is to maintain a reliable, auditable, understandable software project where:

- repository state is authoritative
- AI assistants can safely resume work
- project decisions survive across conversations
- workstreams remain separated
- recommendations remain distinguishable from requirements
- secrets remain protected
- changes are testable
- releases are evidence-based
- production claims are verifiable
- future development remains maintainable

---

# QUICK START

For any project:

```text
PROJECT-SYNC
Repository: owner/repository
```

For NEXUS ICT Data Analyzer:

```text
PROJECT-SYNC
Repository: sajedfallah/nexus-ict
NEXUS-DATA
```

For NEXUS ICT Signal Bot:

```text
PROJECT-SYNC
Repository: sajedfallah/nexus-ict
NEXUS-BOT
```

For NEXUS autonomous Market Signal Agent:

```text
PROJECT-SYNC
Repository: sajedfallah/nexus-ict
NEXUS-SIGNAL
```

For NEXUS shared contracts:

```text
PROJECT-SYNC
Repository: sajedfallah/nexus-ict
NEXUS-CORE
```

---

# IMPORTANT

`NEXUS-SYNC` is not used.

`PROJECT-SYNC` is the single universal project synchronization command.

Repository-specific workstream commands are selectors used after `PROJECT-SYNC`; they are not replacements for it.
