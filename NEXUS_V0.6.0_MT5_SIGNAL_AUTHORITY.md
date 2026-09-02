# NEXUS v0.6.0 — MT5 Signal Authority

## Authority model
- MT5 Admin EA is the only signal issuer.
- NEXUS Core persists, audits and distributes canonical MT5 signals.
- Licensed MT5 client EAs are the only execution endpoints.
- Telegram is retained for subscriptions, reports, statistics and non-operational notices only.
- Telegram signal create/edit/cancel/close handlers are not registered at runtime.

## Canonical flow
`MT5 Admin -> NEXUS API -> Licensed MT5 EAs -> Broker`

## Admin MT5 signal UI
Open the EA **SIGNAL** tab while authenticated in Admin mode. Enter Symbol, Entry, SL, TP1 and Risk; choose BUY/SELL and MARKET/LIMIT; press **ISSUE SIGNAL**. The EA calls `POST /api/v1/admin/mt5/signals`.

## Fail-safe
- Existing broker-side SL/TP remain local protection.
- Backend outage does not create new execution authority.
- Client EAs receive only `issuer_type=MT5_ADMIN` signals.
- Screenshot/chart capture is optional telemetry and never an execution prerequisite.

## Audit
New tables: `signal_events_v060`, `signal_deliveries_v060`, `mt5_heartbeats_v060`.
Signals receive `signal_uuid`, `revision`, `issuer_type`, `issuer_account`, and `issued_at`.

## Migration
1. Keep v0.5.8 online as rollback.
2. Deploy v0.6.0 to a new directory.
3. Copy the existing `.env` into the new directory; do not commit it.
4. Start API and Telegram services from the v0.6.0 root.
5. Compile the v0.6.0 EA in MetaEditor.
6. Add the API URL to MT5 WebRequest allow-list.
7. Authenticate the Admin EA and test with a demo client.
8. Confirm the client receives the signal and execution lifecycle is recorded.
9. Only after successful demo validation, stop using the old Telegram Signal Center.
