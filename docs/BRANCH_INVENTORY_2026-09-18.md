# GitHub Branch Inventory — 2026-09-18

Repository: `sajedfallah/telegrab-signal-bot`

Audit method:
- remote branch inventory from GitHub;
- tip date from the branch head commit;
- merge relationship compared against `main`;
- open PR inventory checked separately.

**Important:** GitHub cannot centrally enumerate developer-machine local branches. This document is the authoritative **remote** branch inventory. Developers should prune local branches with `git fetch --prune` and remove local branches after merge.

## Canonical branch

| Branch | Tip | Protected | Status |
| --- | --- | --- | --- |
| `main` | 2026-09-18 | No | **Production / canonical** |

No repository rulesets were present at audit time. GitHub branch metadata reports `main` as unprotected.

## Open PR branches — do not delete without PR decision

| PR | Head branch | Base | State note |
| ---: | --- | --- | --- |
| #48 | `docs/nexus-ict-v22.31-trail07` | `main` | Active, mergeable |
| #46 | `feature/brag-video-v1` | `feature/live-charts-v1` | Active stacked PR |
| #45 | `feature/provider-panel-ui-v1` | `feat/phase1-tenant-foundation` | Draft stacked PR |
| #44 | `feat/phase1-tenant-foundation` | `main` | Draft |
| #43 | `fix/v0661-telegram-lifecycle-truth` | `release/nexus-v0.6.5` | Draft stacked PR |
| #40 | `hotfix/nexus-v065-visual-20260911` | `release/nexus-v0.6.5` | Open |
| #28 | `feature/miniapp-cx-v2-p0-shell` | `main` | Draft |
| #25 | `feature/nexus-miniapp-v1-v4` | `release/nexus-v0.6.5` | Draft |
| #22 | `feature/academy-v2-morning-8am` | `feature/academy-mentor-agent-vps-6f36` | Open stacked PR |
| #24 | `feature/nexus-daily-stickers` | `feature/v065-integrated-release` | Open stacked PR |
| #21 | `feature/academy-mentor-agent` | `feature/academy-mentor-agent-vps-6f36` | Open |
| #20 | `feature/academy-mentor-agent` | `feature/v065-integrated-release` | Duplicate head / different base |
| #19 | `feature/morning-package-daily-sticker` | `feature/v065-integrated-release` | Open stacked PR |
| #15 | `feature/nexus-hub-academy-channel` | `feature/v065-integrated-release` | Draft |
| #14 | `feature/nexus-hub-academy-channel` | `main` | Duplicate head / different base |
| #11 | `fix/v065-close-reply-hardening` | `main` | Draft |
| #9 | `fix/v063-complete-hardening` | `main` | Draft |
| #8 | `nexus-v060-current-debug-handoff` | `main` | Open historical |

The old stacked-PR structure is the main source of branch sprawl. New work must use short-lived branches from `main`.

## PRs closed during this audit

- **#49** — `vercel-miniapp`: closed as superseded by production PR #51 and governance PR #52.
- **#6** — `docs/repo-standardization-v7.1.0`: closed as superseded by governance PR #52.

Their branches still exist remotely and remain cleanup candidates; closing a PR does not delete a non-merged branch.

## Fully contained in main — deletion candidates

The branch head is already an ancestor of `main`:

- `bootstrap-v7-import`
- `feature/customer-faq-nexus-vip-autotrade-delivery`
- `fix/v060-end-to-end-execution`
- `nexus-miniapp-trust-ui-v5`
- `release/vercel-miniapp-approved`

These are safe cleanup candidates after confirming no external automation refers to the branch name.

## Operational / preview branches requiring cleanup decision

- `ops/telegram-miniapp-url` — one-time Telegram Bot API operation completed on 2026-09-18. Do **not** merge its temporary workflow into `main`; delete after retaining this audit record.
- `vercel-miniapp-e2862c7` — approved Mini App source line used to prepare PR #51; production content is now on `main`. Retain only if historical comparison is needed.
- `vercel-ui-reference-v8` — old UI reference; superseded.
- `vercel-user-miniapp-final` — old Mini App branch; superseded.
- `backup/pre-live-charts-20260914` — explicit backup branch; archive-only.
- `feature/live-charts-v1` — original Live Charts development line; production Mini App now ships from `main`. Keep only for unfinished non-production work.
- `feature/v066-miniapp-auto-setup-fixed-volume` — recent legacy-line development; requires owner decision before deletion.
- `integration/v066-release-reconcile` — recent integration line; requires owner decision.
- `release/nexus-v0.6.5` — historical release line still used as base by open PRs #25, #40 and #43; do not delete until those PRs are resolved.
- `feature/nexus-agent-system-v1` — recent active development; retain.

## Stale / historical branches without an identified active PR

These branches are not fully contained in current `main` and have no open PR identified in this audit. They should **not** be merged wholesale. Review any unique commits, cherry-pick only needed changes onto a fresh branch from `main`, then delete the historical branch.

- `codex/integrate-miniapp-admin-v065`
- `codex/web-mt5-chart-capture`
- `feat/admin-signal-center-bold-controls`
- `feat/admin-v3-symbols-trailing-theme`
- `feat/user-miniapp-final-polish-v1`
- `feat/user-option3-theme-only`
- `feat/v065-user-ux-hardening`
- `feature/agentic-content-gemini`
- `feature/analysis-center-multisymbol`
- `feature/content-editorial-taxonomy`
- `feature/free-signal-community-topic`
- `feature/miniapp-admin-control-center-v1`
- `feature/miniapp-landing-poster-v6`
- `feature/miniapp-landing-reopen-v5`
- `feature/miniapp-landing-v5`
- `feature/miniapp-navigation-back-v7`
- `feature/miniapp-payment-onboarding-v4`
- `feature/miniapp-polish-intelligence-v3`
- `feature/performance-marketing-engine-v1`
- `feature/public-dual-channel-daily-report`
- `feature/v065-professional-news-engine`
- `fix/landing-approved-final-direct-asset`
- `fix/user-landing-direct-webp-v10`
- `integration/nexus-v065-platform`
- `ops/admin-v3-deploy-helper`
- `ops/landing-v10-fix-deploy-helper`
- `ops/user-final-polish-deploy-helper`
- `ops/user-option3-theme-deploy-helper`
- `release/nexus-autotrade-ui65-production-20260907`
- `sync/v0.5.8-final-source`

## Other branch dependencies / support branches

The following exist primarily because current historical PRs use them as bases or they represent old release integration lines. Resolve dependent PRs first:

- `feature/academy-mentor-agent-vps-6f36`
- `feature/v065-integrated-release`

## Cleanup order

1. Close/merge open PRs that are still valuable.
2. Superseded PRs #49 and #6 are already closed; review and delete their branches when no historical reference is required.
3. Retarget valuable stacked PRs to `main` where practical.
4. Delete fully merged branches.
5. For diverged stale branches, inspect unique commits; cherry-pick only approved changes to a fresh branch from `main`.
6. Delete superseded Vercel/ops branches.
7. Run `git fetch --prune` on developer clones.

Never force-merge a historical branch merely to reduce branch count.
