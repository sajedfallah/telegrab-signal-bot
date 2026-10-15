# V3.3 VPS regression evidence

Source: complete PowerShell transcript supplied directly by the user in this chat.
Codex did not run the commands on the VPS. The transcript establishes the tested
commit explicitly, unlike the earlier six-test baseline evidence.

Test root: C:\NEXUS_AGENT_TEST
Branch: feature/nexus-agent-system-v1
Tested commit: 7fe7f8ff58b174cd83ba1e7c632de34371783cbf

The verification script checked the bundle, fetched its branch and fast-forwarded
the checkout from d973a0a to 7fe7f8f. HEAD was printed twice as the full SHA above.
The initial and final git status both showed only the untracked data/ directory.
The transcript does not establish a GitHub push: the script explicitly does not
push, publish, start services or deploy.

## Executed results

| Suite | Actual VPS output | Scope |
|---|---|---|
| Baseline pytest: tracker, lifecycle, full ICT gate | 10 passed in 2.22s | PASS |
| V3.2 recovery unittest harness | Ran 10 tests in 0.695s; OK | PASS |
| Full isolated V3.3 unittest discovery | Ran 56 tests in 21.400s; OK | PASS |

The recovery harness repeats six baseline test functions, so the three execution
counts must not be described as 76 distinct test cases. No failed assertion or
execution error appears in the supplied transcript.

## Gate update

- VPS transfer and exact tested SHA: VERIFIED.
- Focused regression execution on the authorized VPS: PASS for these suites.
- Isolated persistence, chronology, crash/restart, expiry and deduplication tests:
  PASS within their fixture coverage.
- Detector equivalence: FAIL. Passing characterization tests reproduce actual
  disagreements in selected FVG identity, post-MSS chronology and forming-bar MSS.
- Actual broker feed/calibration acceptance: NOT VERIFIED. Fixture/export-reader
  tests do not establish compatibility of the running broker feed.
- Signal Watcher integration: BLOCKED and unchanged.
- Overall V3.3 phase/release: BLOCKED, not PASS.
- GitHub availability of the tested commit: NOT established by this transcript;
  all four commits arrived on the VPS through the local bundle.

No source code change or test rerun is needed merely to record this evidence.
The next code-development task is an isolated shared closed-candle detector with
exact setup/evidence identity and comparison tests before any runtime migration.
The tested development commit can be pushed from the authorized VPS using the
existing guarded helper, which rejects unexpected remote HEAD and never forces.
