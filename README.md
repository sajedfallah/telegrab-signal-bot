# NEXUS

> **Canonical repository:** `sajedfallah/telegrab-signal-bot`  
> **Canonical branch:** `main`  
> **Last repository status update:** 2026-09-18  
> **Core source baseline:** NEXUS Core v7.0.3  
> **Current Mini App release lineage:** PR #51 / `ccaaa11f80805efad148536479ad377b9e9190d9`  

NEXUS is the Telegram trading platform that contains the Telegram bot, Mini App, subscription/payment flows, AutoTrade integration, MT5 components, signal lifecycle, content/academy modules, and supporting APIs.

## Project dashboard

| Area | Canonical source / route | Current status |
| --- | --- | --- |
| GitHub production branch | `main` | Canonical |
| Vercel project | `telegrab-signal-bot` / `prj_5MA4Bz9EelogSiiqj9vSrK8Yw5NS` | Active |
| Vercel root directory | `miniapp` | Active |
| Mini App production | https://telegrab-signal-bot.vercel.app/ | READY |
| Main branch alias | https://telegrab-signal-bot-git-main-fallahsajed-2126s-projects.vercel.app/ | Production alias |
| Backend/API | https://api.nexustrade.ir | VPS source of truth |
| Mini App API proxy | `/miniapp/api/*` -> `https://api.nexustrade.ir/miniapp/api/*` | Active |
| Telegram Mini App URL | https://telegrab-signal-bot.vercel.app/ | Configured in BotFather |
| Telegram menu button | `ورود به نکسوس` -> production Mini App | Configured |
| Live Charts market truth | NEXUS / MT5 feed via VPS API | Active |
| Branching model | Trunk-Based Development | Canonical policy |
| Detailed deployment map | [docs/DEPLOYMENT_BRANCHING.md](docs/DEPLOYMENT_BRANCHING.md) | Canonical |
| Branch inventory | [docs/BRANCH_INVENTORY_2026-09-18.md](docs/BRANCH_INVENTORY_2026-09-18.md) | Audit snapshot |

## Current architecture

The Mini App frontend is hosted on Vercel. Long-running services remain on the Windows VPS.

```text
Telegram
   |
   v
Vercel Mini App
https://telegrab-signal-bot.vercel.app
   |
   | /miniapp/api/*
   v
NEXUS VPS API
https://api.nexustrade.ir
   |
   +--> Telegram Bot / subscriptions / payments
   +--> AutoTrade
   +--> MT5 / broker truth
   +--> Live Charts market feed
```

Vercel must not contain the bot token, MT5 secrets, broker credentials, payment secrets, or other VPS runtime secrets. The frontend is static and currently has no required Vercel application environment variables.

## Latest changelog

### 2026-09-18 — Repository / deployment governance consolidation

- Merged PR #52 and established `README.md`, `CONTRIBUTING.md`, deployment/branching documentation, branch inventory and project dashboard.
- Added repository governance CI and safe merged-branch housekeeping.
- Normalized GitHub Actions to PR/`main` triggers instead of historical feature-branch triggers.
- Closed superseded PR #49 (old Vercel preparation) and PR #6 (old repository standardization).
- Deleted six audited obsolete/merged remote branches, reducing the remote branch count from 67 to 61.
- Vercel production redeployed from `main` successfully and remained `READY`.

### 2026-09-18 — Vercel Mini App production cutover

- Merged PR #51: approved Vercel Mini App frontend into `main`.
- Released the approved minimal NEXUS landing page.
- Production Mini App now serves Home, Signals, Live Charts, Plans and Account from Vercel.
- Vercel `miniapp/vercel.json` proxies `/miniapp/api/*` to the existing VPS API.
- Production deployment is `READY`; canonical URL is `https://telegrab-signal-bot.vercel.app/`.
- BotFather Main Mini App URL was changed to the canonical Vercel production URL.
- Telegram default menu button was changed to `ورود به نکسوس` and points to the canonical Vercel production URL.
- Live Charts remain broker/MT5-truth backed; no synthetic Gold/Forex candles are introduced.
- Backend, AutoTrade execution, MT5 runtime and Telegram lifecycle were not moved to Vercel.

### Core v7.0.3 baseline

See [NEXUS_V7_0_3_FIX_REPORT_FA.md](NEXUS_V7_0_3_FIX_REPORT_FA.md). The baseline includes Telegram menu/guide hardening, FastAPI lifespan migration and regression validation.

## Vercel environments

| Environment | Source | URL | Trigger |
| --- | --- | --- | --- |
| Development | Developer workstation | `http://127.0.0.1:8088` for UI-only static preview | Manual local run |
| Preview / pre-production | Any GitHub branch / PR | Vercel generated deployment + branch alias; the exact Preview link is posted by `vercel[bot]` on the PR | Automatic on branch/PR commit |
| Production | `main` | https://telegrab-signal-bot.vercel.app/ | Automatic after commit/merge to `main` |

There is intentionally no permanent `staging` branch. A Vercel PR Preview is the pre-production environment. This avoids another long-lived branch that can drift from `main`.

## New developer quick start

Do not start from old release, Vercel, integration or backup branches. Start from `main`.

```bash
git clone https://github.com/sajedfallah/telegrab-signal-bot.git
cd telegrab-signal-bot
git checkout main
git pull --ff-only
git switch -c feature/<short-description>
```

Python backend setup:

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create local runtime configuration from `.env.example`. Never commit `.env`.

UI-only local preview:

```bash
python -m http.server 8088 --directory miniapp
```

Open `http://127.0.0.1:8088`. Telegram-authenticated pages require valid Telegram `initData`; use a Vercel Preview opened from Telegram for authenticated E2E validation.

Run the current CI-equivalent checks before opening a PR:

```bash
python -m compileall -q app run.py run_api.py
python -m pytest tests/test_miniapp_api.py -q
python -m pytest tests/test_agentic_content_mvp.py tests/test_free_signal_topic_routing.py tests/test_customer_experience.py -q
```

Full contribution and PR policy: [CONTRIBUTING.md](CONTRIBUTING.md).

## Branching policy

NEXUS uses **Trunk-Based Development with short-lived branches**.

Allowed prefixes:

- `feature/` — new capability
- `bugfix/` — normal defect fix
- `hotfix/` — urgent production correction
- `release/` — short-lived coordinated release candidate only
- `docs/` — documentation-only change
- `ops/` — operational automation / infrastructure task

A branch should normally live for hours or a few days, not weeks. Merge through a PR, then delete it after merge. Avoid stacked long-lived branch chains unless explicitly documented.

## Pull request requirements

Before merge to `main`:

1. Scope is clear and based on the latest `main`.
2. Required GitHub Actions are green.
3. Vercel Preview is `READY`.
4. Functional change is reviewed.
5. Production-impacting changes include rollback notes.
6. No `.env`, tokens, credentials, database files or generated runtime files are tracked.
7. For Mini App changes, the PR Preview is opened from Telegram when authenticated behavior changed.

Vercel Git integration is active and posts the exact Preview link in the PR conversation.

## Repository governance notes

- `main` is the production branch and should be protected in GitHub settings.
- Audit on 2026-09-18 found no repository rulesets and branch metadata reported `protected: false`. Protection must be configured in GitHub Settings because the connected GitHub integration cannot mutate branch-protection settings.
- Recommended `main` protection: PR required, at least one approval, required CI checks, require branch up to date, block force-push and deletion.
- GitHub currently has historical/stale branches. The authoritative inventory and deletion candidates are in [docs/BRANCH_INVENTORY_2026-09-18.md](docs/BRANCH_INVENTORY_2026-09-18.md).
- New merged branches are cleaned by repository housekeeping automation only when no open PR depends on the branch as a base.

## Required repository files

| File | Status |
| --- | --- |
| `README.md` | Present |
| `CONTRIBUTING.md` | Present |
| `LICENSE` | Present — proprietary/all rights reserved |
| `.gitignore` | Present |
| `miniapp/vercel.json` | Present |
| `.github/workflows/` | Present |
| `CODE_OF_CONDUCT.md` | Not required while the repository is operated as an internal/commercial project; add before opening community contribution |

## Do not do

- Do not deploy VPS/backend runtime from Vercel.
- Do not put production secrets in Vercel frontend variables or source code.
- Do not use old `vercel-*`, `integration/*`, `backup/*` or historical release branches as a new development baseline.
- Do not reset/clean the production VPS to match Git history.
- Do not manufacture Gold/Forex prices or candles; broker/MT5 remains the source of truth.
