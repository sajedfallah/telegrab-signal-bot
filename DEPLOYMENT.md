# NEXUS Deployment Contract

## Production boundaries

NEXUS has two deployment surfaces.

### Frontend

- Source: `miniapp/`
- Host: Vercel
- Production branch: `main`
- Production URL: `https://telegrab-signal-bot.vercel.app/`
- API requests under `/miniapp/api/*` are rewritten to the VPS API.

### Backend / Telegram / MT5

- FastAPI entrypoint: `run_api.py`
- FastAPI application: `app.combined_api:app`
- Telegram process entrypoint: `run.py`
- MT5 EA source: `mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5`
- Backend authority remains the Windows VPS / `api.nexustrade.ir`.

## Startup contract

API:

```text
run_api.py
-> app.combined_api:app
-> app.autotrade.api.app
   + Mini App user router
   + Mini App admin router
   + /miniapp static mount when local directory exists
```

Telegram:

```text
run.py
-> installs feature routers/patches
-> app.main.main
-> aiogram Dispatcher
-> long polling
```

## Reverse proxy

Repository evidence defines the application ports/routes but does not currently contain a canonical Caddy/Nginx production configuration. Therefore reverse-proxy state is deployment-side and must be verified on the VPS before a release is declared production-ready.

## Release gate

Before backend deployment:

1. Branch from current `main`.
2. Run repository CI-equivalent checks.
3. Review diff for secret/runtime artifacts.
4. Verify API startup/import path.
5. For MT5 changes, compile the exact EA source and compare the deployed artifact hash.
6. Verify production health and required API paths.
7. Keep rollback to the prior known-good source/artifact.

Before frontend deployment:

1. Use Vercel Preview on the PR.
2. Validate static rendering.
3. For authenticated behavior, open Preview through Telegram with valid initData.
4. Merge only after checks pass.

No deployment should be marked PASS when reverse proxy, process state, MT5 artifact identity or authenticated Telegram behavior was not actually verified.
