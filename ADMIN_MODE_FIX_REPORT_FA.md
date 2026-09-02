# NEXUS Admin Mode Fix

## Root cause
The previous build had three integration defects:
1. FastAPI did not map `X-NEXUS-Admin-Mode` / `X-NEXUS-Admin-Token` because Header() used the wrong implicit aliases.
2. Some MT5 control endpoints still required a customer license before attempting admin authorization.
3. The EA could enter the customer license wizard during startup before automatic owner-account detection.

## Fix
- Owner MT5 account `80127028` is recognized automatically by the EA.
- Admin token is sent using the exact `X-NEXUS-Admin-*` headers.
- Backend validates both allow-listed MT5 account and server-side admin token.
- Admin sessions do not require a customer license.
- Activate, license/check, heartbeat, signals, commands, trade-event and receipt paths support admin authentication.
- Normal customer license flow remains unchanged for non-admin accounts.

## Owner configuration
`NEXUS_ADMIN_MT5_ACCOUNTS=80127028`
`NEXUS_ADMIN_TOKEN` is configured in `.env` and must match the EA's owner token.
