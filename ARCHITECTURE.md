# NEXUS Repository Architecture

Status: canonical architecture contract for `telegrab-signal-bot`.
Baseline audited: `main@00336bc6e58eb434ed5ed89e95e0e444a4d6d72e`.

## Scope

This repository owns the NEXUS Signal Platform. NEXUS AutoTrade and NEXUS CopyTrade as separate projects must not be merged into this repository unless their code is already part of the explicit runtime contract here.

## Canonical runtime map

| Concern | Canonical source of truth | Notes |
| --- | --- | --- |
| Telegram runtime | `run.py` -> `app.main.main` | aiogram polling runtime; feature routers are installed by `run.py`. |
| Telegram core handlers | `app/main.py` | Stable legacy core plus lifecycle workers and publication chain. |
| FastAPI process | `app/combined_api.py` | Reuses `app.autotrade.api.app`, then includes Mini App routers. |
| AutoTrade / MT5 API | `app/autotrade/api.py` | Root FastAPI app and `/api/v1/autotrade/*` + MT5/admin endpoints. |
| Mini App user API | `app/miniapp_api.py` | Prefix `/miniapp/api`. |
| Admin Mini App API | `app/miniapp_admin_api.py` | Prefix `/miniapp/api/admin`. |
| Telegram WebApp auth | `app/miniapp_api.py::_validate_init_data` / `_auth_user` | Admin API imports and reuses the same auth path. |
| Signal publication / Telegram lifecycle | `app/main.py` | `_publish_signal`, `_reply_signal_update`, MT5 event worker and final result reply chain. |
| MT5 payload contract | `app/autotrade/service.py::signal_to_payload` | API callers should not independently rebuild the EA wire contract. |
| Database schema and primary data API | `app/db.py` | Canonical database module; remaining direct SQL outside it is tracked technical debt. |
| Configuration | `app/config.py::settings` + environment | Runtime secrets/config stay outside source. |
| User Mini App frontend | `miniapp/index.html` and referenced assets | Static Vercel frontend. |
| Admin Mini App frontend | `miniapp/admin.html` and referenced assets | Static admin UI. |
| Static backend mount | `app/combined_api.py` -> `/miniapp` | VPS static serving path; Vercel remains frontend production host. |
| Signal Agent | `app/signal_agent/*` | Market data, ICT detection, context engine. |
| Tests | `tests/*` | CI-defined subsets plus broader regression suite. |

## Process topology

```text
Telegram users/admins
        |
        v
   aiogram bot
 run.py -> app/main.py
        |
        +------> app/db.py ------> SQLite
        |
        +------> signal publication / lifecycle replies
        |
        +------> background workers

Mini App / Admin Mini App
        |
        v
Vercel static frontend
        |
        | /miniapp/api/*
        v
app/combined_api.py
        |
        +--> app/miniapp_api.py
        +--> app/miniapp_admin_api.py
        +--> app/autotrade/api.py
                     |
                     v
                  MT5 / EA
```

## Signal lifecycle contract

The authoritative lifecycle is:

```text
Signal Created
-> Persisted
-> Telegram Published
-> Telegram message anchor persisted
-> Execution requested
-> MT5 execution / receipt
-> Position opened or pending
-> Partial close / SL / TP / trailing events
-> Final close
-> Result persisted
-> Telegram lifecycle reply
-> Final result reply
```

Canonical identities include the database signal id, public signal code, Telegram message ids, MT5 ticket/position identity and event id. Code that maps between these identities must use persisted relationships rather than reconstructing them from presentation text.

## Known dispersion that remains

1. `app/db.py` is the intended database authority, but direct SQL still exists in `app/main.py`, `app/miniapp_api.py`, `app/miniapp_admin_api.py` and `app/autotrade/api.py`. Moving these queries requires regression tests because several are runtime-critical.
2. `app/main.py` is a large mixed-responsibility legacy core. It remains authoritative until handlers/workers are migrated behind tests; size alone is not evidence for deletion.
3. `miniapp/` intentionally contains layered/versioned assets. Only assets proven unreachable from HTML and JavaScript dependency paths may be removed.
4. Historical release/audit Markdown files in the repository root are records, not canonical current-state documentation. This file, `README.md`, `DEPLOYMENT.md`, `CONFIGURATION.md`, and `TESTING.md` are the current documentation contract.

## Change rule

A concern may have more than one implementation only when the separation is intentional and documented. Any consolidation that changes signal decision logic, risk, TP/SL, trailing, execution gating or broker truth requires explicit behavioral evidence and regression coverage.
