# NEXUS Repository / Deployment Dashboard

Snapshot: **2026-09-18**

| Control | State | Action |
| --- | --- | --- |
| Canonical Git branch | `main` | Use for all new baselines |
| Main branch protected | **No** (`protected:false`; no rulesets) | Enable PR/review/check protection in GitHub Settings |
| Repository live head | `main` | Treat GitHub `main` as the live source; commit SHA changes continuously |
| Vercel production | **READY** | Production source is `main`; canonical URL is stable while deployment IDs rotate |
| Telegram Main Mini App | **Production Vercel URL configured** | No action |
| Vercel PR Preview | **Enabled / verified** | `vercel[bot]` posts a `Ready` Preview on PR; verified on #48 |
| Vercel project duplication | **None for NEXUS** | Keep single project |
| Vercel frontend secrets required | **None** | Keep secrets on VPS |
| API rewrite | **Healthy design** | `/miniapp/api/*` -> VPS |
| Remote branch count | **61** (reduced from 67) | Continue controlled cleanup |
| Audited branches deleted | **6** | Completed: 5 merged + 1 one-time ops branch |
| Open PRs after immediate cleanup | **18** | Continue triage of long-lived/stacked PRs |
| README | Added by governance update | Canonical entry point |
| CONTRIBUTING | Added by governance update | Canonical developer flow |
| LICENSE | Added by governance update | Proprietary/all rights reserved |
| CODE_OF_CONDUCT | Not currently required | Add if public community contribution opens |
| Branching model | Trunk-Based | Short-lived branches |
| Auto branch cleanup | Added | Deletes merged head only if no open PR depends on it |

## Immediate governance priorities

1. Enable GitHub branch protection/rules for `main`.
2. PR #49 and #6 are closed as superseded; their diverged branches remain for explicit historical review before deletion.
3. Retarget or close long-lived stacked PRs so future work starts from `main`.
4. Keep the Vercel project count at one for NEXUS.
5. Keep Telegram on the canonical Vercel production domain, not ephemeral deployment URLs.
