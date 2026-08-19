# NEXUS — Latest Version

**Current latest tested snapshot: NEXUS v7.0.6**  
**MT5 Auto Trade EA source: v0.4.3**

This snapshot is the current Telegram Bot + FastAPI + MT5 AutoTrade baseline after local execution testing on 2026-08-19.

## Included status

- Telegram signal bot core
- FastAPI AutoTrade backend
- MT5 AutoTrade source and required Include files
- License activation and MT5 account binding
- Signal polling and execution pipeline
- Duplicate signal / duplicate trade protection
- Broker symbol mapping
- Entry-deviation controls
- MARKET / LIMIT signal support
- Trade execution diagnostics and retry-safe signal cursor
- NEXUS trailing profiles 01–07
- User/admin guide flows and AutoTrade reporting foundation
- Automated regression suite: **47 passed**

## Canonical clean snapshot

The clean source archive is stored in this repository under:

```text
.bootstrap/v706/part00 ... part04
.bootstrap/v706/MANIFEST.json
```

Archive SHA-256:

```text
3b42d06e3f2456a84a9a57f2222d9ee1d3c632422cc2061c33813cb841771fc8
```

Security note: `.env`, Telegram token, runtime databases, logs, backups, cache files and compiled `.ex5` binaries are intentionally **not committed**.
