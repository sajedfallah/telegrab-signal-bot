# NEXUS v0.6.0 — Execution + Telegram Fix

## Fixed
- Admin heartbeat/auth responses can no longer revoke `allow_new` / `allow_manage` after successful Admin authentication.
- Admin Issue Signal forces an immediate poll of exactly the newly-created canonical signal instead of relying on a stale cursor.
- Signal polling now emits explicit diagnostic logs when blocked or when the API request fails.
- Admin Issue Signal captures the active chart before POST and temporarily hides all `NXS.UI.*` objects; the Admin panel is therefore excluded from the Telegram screenshot.
- The screenshot is sent as `chart_base64` to the MT5 Admin API.
- MT5 Admin signal creation remains `ACTIVE` and Telegram publication is reporting-only.
- Telegram publication is queued as a FastAPI background task so Telegram latency cannot cause the MT5 HTTP request to time out and create duplicate signals.
- FREE/VIP publication IDs and errors are recorded in the signal event log.

## Validation
- Python syntax check: PASS
- Automated test suite: **170 passed, 3 skipped**
- MQL5 source was statically reviewed and prepared for MetaEditor compilation. A final zero-warning claim requires compiling this exact source in the user's MetaEditor environment.
