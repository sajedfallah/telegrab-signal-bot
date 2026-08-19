# NEXUS — Latest Version

**Current latest tested milestone: NEXUS v7.0.6**  
**MT5 Auto Trade EA source: v0.4.3**

This is the latest version marker for the Telegram Bot + FastAPI + MT5 AutoTrade development line after local execution testing on 2026-08-19.

## Confirmed status

- Telegram signal bot core operational
- FastAPI AutoTrade backend operational
- MT5 AutoTrade license activation operational
- Auto signal polling/execution confirmed in local test
- Duplicate signal / duplicate trade protection retained
- Broker symbol mapping retained
- Entry-deviation controls retained
- MARKET / LIMIT foundations retained
- Trade execution diagnostics and retry-safe signal cursor retained
- NEXUS trailing profiles 01–07 retained
- Automated regression suite: **47 passed**

## Repository security policy

Runtime secrets and state remain local and are not committed:

- `.env`
- Telegram bot tokens / credentials
- `nexus_bot.db`
- `nexus_fsm.db`
- logs / backups / caches
- compiled customer `.ex5` binary

Use `VERSION` and this file as the repository marker for the latest tested development milestone.
