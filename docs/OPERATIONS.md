# Operations Guide — NEXUS v7.0

## Supported baseline

- Python 3.11
- Windows development/operation path is documented and tested
- aiogram 3.x
- SQLite
- Telegram long polling

## First installation

```cmd
py -3.11 -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt --timeout 120 --retries 10
copy .env.example .env
```

Edit `.env`, then:

```cmd
python run.py
```

Or use:

```cmd
setup_windows.bat
start_windows.bat
```

## Required configuration categories

- bot token
- admin Telegram IDs
- public channel ID/URL
- FREE signal channel ID or public username/URL
- VIP channel ID
- support contact
- Rial payment card/owner label
- timezone
- reminder days
- plan prices

Optional/config-gated:

- USDT wallet/network/plan prices
- Auto Trade channel URL
- channel report language
- metal pip sizes

## Runtime files — never commit

- `.env`
- `nexus_bot.db`
- `nexus_fsm.db`
- `venv/`
- logs
- backups
- generated cache/pyc files

## Starting / stopping

Start with one process only. Long polling should not be run from multiple copies of the same bot token at the same time.

Graceful stop: `Ctrl+C` in the active terminal.

Persistent FSM means payment/signal workflow state should survive a normal restart, but always test critical workflows after changing storage code.

## Backup

The bot contains backup behavior in the stable core. For real production use, maintain at least one backup copy **off the same disk/machine**. A local-only backup does not protect against disk loss.

Recommended future v7.1 work:

- encrypted off-host backup
- restore test command/checklist
- backup health timestamp in admin system status

## Telegram channel permissions

The bot must have sufficient administrator permissions in channels where it:

- publishes signals/reports
- approves join requests
- removes expired VIP users
- revokes/creates invite links as required

FREE channel may be addressed by public username when applicable. Private channels require numeric ID.

## Report schedule

Defaults:

- daily: `23:59`
- weekly: Friday `23:59`
- timezone: `Asia/Tehran`

`REPORT_CATCHUP_ENABLED=false` is recommended if you do not want historical reports dumped after a restart.

## Incident checklist

### Bot does not start

1. confirm Python 3.11
2. activate venv
3. install requirements
4. verify `.env`
5. verify only one bot instance is polling
6. inspect console/log file

### Signal sends to one channel only

1. check destination stored on signal
2. verify FREE/VIP IDs/usernames
3. check bot channel permissions
4. use Retry Publication
5. inspect stored FREE/VIP message IDs

### Break Even/update/result does not reply

1. verify original signal publication stored message ID
2. verify last-message ID chain
3. check channel permissions
4. inspect Telegram API errors
5. avoid marking state successful if all channel publications failed

### SQLite locked

v7 lineage uses WAL/busy timeout hardening. If lock errors persist, check for multiple bot processes or external processes holding the DB.

## Production readiness next step

v7.0 is the baseline. v7.1 should add system health checks, duplicate-instance prevention, queueing/retry observability and verified backup restore procedures before major new product surface area.
