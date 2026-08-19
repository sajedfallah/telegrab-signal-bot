# NEXUS v7.0.6

Latest locally tested NEXUS Telegram + FastAPI + MT5 AutoTrade milestone.

## Confirmed in the current test cycle

- Telegram signal publishing works.
- FastAPI AutoTrade backend runs alongside the Telegram bot.
- MT5 AutoTrade EA license activation works.
- Auto signal polling/execution path was confirmed working locally.
- EA source version: `0.4.3`.
- Broker symbol mapping supports broker prefixes/suffixes such as `XAUUSD.EC` and similar variants.
- Signal execution diagnostics show receive/entry/execution/reject state.
- Retry-safe signal cursor prevents transient execution failures from silently consuming a signal.
- Duplicate signal/trade protection is retained.
- MARKET/LIMIT and entry-deviation foundations are included in the current development baseline.
- Regression suite: **47 passed**.

## Security / repository policy

Do not commit runtime secrets or state. The following stay local only:

- `.env`
- Telegram bot tokens / credentials
- `nexus_bot.db`
- `nexus_fsm.db`
- logs and backups
- compiled `.ex5` customer binary

The repository should contain only safe source/config examples and version documentation.
