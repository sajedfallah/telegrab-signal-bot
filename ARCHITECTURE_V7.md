# NEXUS CORE v7 Architecture

## What changed

v7 starts the modular split of the Telegram core without rewriting stable payment/signal handlers all at once.

- `app/states.py` — all FSM state declarations.
- `app/storage/sqlite_storage.py` — persistent aiogram FSM state/data storage.
- `app/services/license_service.py` — access/entitlement and license activation logic.
- `app/services/analytics_service.py` — signal analytics aggregation.
- `app/routers/analytics.py` — isolated analytics admin router.
- `app/routers/subscriptions.py` — isolated plan entitlement/renewal admin router.
- `app/main.py` — stable legacy handlers, workers and publishing pipeline. New modules are registered alongside it and can be migrated incrementally.

## Persistent FSM

`nexus_fsm.db` is created beside `nexus_bot.db`. Payment, promo, signal-creation and close flows keep their FSM state across a normal bot restart. The FSM file is excluded by `.gitignore`/`*.db`.

## License model

Plans now own an entitlement snapshot:

- VIP channel access
- Auto Trade access
- renewal discount
- upgrade rank (reserved for future sorting/upgrade UI)

When a payment is approved, the license snapshots the plan access fields. Admin-issued licenses still grant both VIP and Auto Trade by default. Trial access is VIP-only.

Early renewal appends time to the current expiry. Upgrading to a plan with additional access enables the new access immediately and keeps remaining time.

## Analytics

Signal Center -> Analytics Dashboard supports:

- 7 days / 30 days / all time
- total closed trades, win/loss/BE, win rate
- raw direction-aware return %
- Forex pips and Crypto % totals
- average R:R
- breakdown by symbol
- breakdown by NEXUS trailing model
- Free vs VIP channel comparison

## Compatibility

The v6 database is migrated in place. Existing licenses are backfilled with both VIP and Auto Trade access to preserve previous behavior.
