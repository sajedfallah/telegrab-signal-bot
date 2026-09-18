# Contributing to NEXUS

## 1. Canonical baseline

All new work starts from `main`.

```bash
git checkout main
git pull --ff-only
git switch -c feature/<short-description>
```

Do not branch from old `release/*`, `vercel-*`, `integration/*`, `backup/*` or another developer's feature branch unless the PR is intentionally stacked and that dependency is documented.

## 2. Branch naming

Use one of:

- `feature/<topic>`
- `bugfix/<topic>`
- `hotfix/<topic>`
- `release/<version-or-purpose>`
- `docs/<topic>`
- `ops/<topic>`

Keep branches short-lived. After merge, delete the branch unless another open PR still uses it as its base.

## 3. Local setup

Python 3.11 is the CI baseline.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and use non-production values for local development. `.env` is never committed.

Mini App UI-only preview:

```bash
python -m http.server 8088 --directory miniapp
```

For full Mini App integration, rely on the Vercel Preview generated for the PR and open it from Telegram so valid `initData` is present.

## 4. Required checks before PR

```bash
python -m compileall -q app run.py run_api.py
python -m pytest tests/test_miniapp_api.py -q
python -m pytest tests/test_agentic_content_mvp.py tests/test_free_signal_topic_routing.py tests/test_customer_experience.py -q
```

Run additional tests for the subsystem you changed.

## 5. Pull request flow

1. Rebase or update your branch from the current `main`.
2. Push the branch.
3. Open a PR into `main`; the repository PR template must be completed.
4. Wait for GitHub Actions.
5. Wait for the Vercel Preview to reach `READY`.
6. Use the Vercel Preview link posted by `vercel[bot]` in the PR.
7. Review functional changes; for authenticated Mini App changes, validate from Telegram.
8. Merge only after required checks are green.
9. Delete the source branch after merge unless it is still used as the base of another open PR.

## 6. Mandatory merge conditions

The intended repository policy is:

- PR required for `main`.
- At least one review approval.
- Required checks green.
- Vercel Preview successful for frontend changes.
- No unresolved blocking review.
- No tracked secrets or runtime databases.
- No force-push to `main`.

GitHub branch protection is not yet technically enforced by a ruleset as of 2026-09-18. Treat these requirements as mandatory team policy until protection is enabled in GitHub Settings.

## 7. Vercel behavior

The linked Vercel project is `telegrab-signal-bot`; Root Directory is `miniapp`.

- PR/branch commit -> automatic Preview deployment.
- Merge/push to `main` -> automatic Production deployment.
- Production URL -> https://telegrab-signal-bot.vercel.app/
- API requests under `/miniapp/api/*` are rewritten to https://api.nexustrade.ir.

No application secrets are required on the Vercel frontend. Production secrets remain on the VPS.

## 8. PR template and review evidence

Every PR should complete `.github/PULL_REQUEST_TEMPLATE.md`. For Mini App work, include the Vercel Preview URL or confirm the `vercel[bot]` Preview is `Ready`. For authenticated UI changes, record Telegram E2E validation with valid `initData`.

## 9. Production boundaries

Changes to frontend deployment must not silently alter:

- Telegram lifecycle
- AutoTrade execution gating
- MT5 broker truth
- production database
- VPS-only files
- payment or bot credentials

If a change touches one of these areas, state the production impact and rollback plan in the PR.
