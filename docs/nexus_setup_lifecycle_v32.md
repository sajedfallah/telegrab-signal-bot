# NEXUS V3.2 — Shadow-only POI binding and optional persistence

This release does not modify live execution or the automatic signal watcher.

- Manual /analysis M1 and /analysis M5 call setup_lifecycle_v32.observe_configured.
- Tracker scans closed candles and records a stable ID derived from sweep timestamp.
- A candidate setup is bound only when its sweep candle intersects a directional,
  non-TOO_WIDE FVG/OB/Daily Quadrant candidate returned by scan_pois.
- POI selection is provisional: origin, mitigation history and forward validity
  are **not** independently confirmed.
- Opt-in SQLite path via NEXUS_AGENT_SETUP_DB_PATH. If missing, no DB is written,
  and the Telegram checklist displays VOLATILE.
- Changed bound POI invalidates a stored setup; stages do not regress.
- RETEST_OBSERVED does not authorize a signal. Publication remains under
  existing hard risk / full ICT gate.

Test-host PowerShell:

```powershell
cd C:\NEXUS_AGENT_TEST
$env:NEXUS_AGENT_SETUP_DB_PATH = "C:\NEXUS_AGENT_TEST\data\setup_lifecycle_v32.db"
python -m pytest tests/test_agent_setup_tracker_v31.py tests/test_agent_setup_lifecycle_v32.py -q
```

Do not set the path inside C:\NEXUS_DEPLOY or reuse the production database.
Do not run duplicate Telegram polling processes.

Known limits: persistence is wired into manual /analysis, not the background
watcher yet. This is an observation journal, not a trade-event ledger. Historical
POI genesis/mitigation and strict stage-to-stage event attribution are upcoming.
