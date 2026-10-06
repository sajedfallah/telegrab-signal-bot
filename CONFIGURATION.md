# NEXUS Configuration Contract

Runtime configuration is environment-driven. The canonical Python access layer is `app/config.py::settings`; `.env.example` documents supported deployment values.

## Rules

- Never commit `.env`, bot tokens, API keys, broker credentials, encryption keys, payment secrets or production database files.
- Prefer adding a setting to `app/config.py` over introducing new scattered `os.getenv()` calls.
- Frontend runtime configuration must remain non-secret. Vercel must not receive VPS secrets.
- Production API host/rewrite behavior is defined by `miniapp/vercel.json` and deployment documentation.
- MT5/Admin account allow-lists and admin authentication values are server-side only.

## Current configuration sources

| Source | Role |
| --- | --- |
| `.env.example` | Supported configuration template, no real secrets. |
| `app/config.py` | Canonical typed/runtime settings object. |
| Environment variables | Deployment-specific values and secrets. |
| `miniapp/vercel.json` | Static frontend rewrite/deployment contract. |
| Selected legacy direct `os.getenv()` reads | Compatibility debt; migrate only with regression coverage. |

## Known direct environment consumers

The audit confirmed direct environment reads remain in runtime code, including Mini App auth/receipt limits, bot username, Telegram resolver behavior and API host/port startup. These are not automatically unsafe, but new configuration should be centralized unless there is a documented bootstrap reason.

## Security

A value belongs in source only when it is public configuration or a safe example. Real credentials discovered during audits must be reported only by file/path/type and never printed.
