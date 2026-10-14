# NEXUS Channel Collector V1 (test only)

Separate, authorized **read-only** Telegram user session. Not the Telegram Bot API,
not NEXUS production services, and not the auto-trading system. Collector NEVER joins
channels automatically, changes memberships or publishes messages.

## Account setup

Use a dedicated Telegram account if available. A personal account also works.
Obtain API ID and API Hash for that account from https://my.telegram.org .
Do not post credentials or login codes in chat.

On Windows PowerShell, enter the values on the test host. For the API Hash,
use Read-Host -AsSecureString and store under Windows User environment.
Treat *.session files as highly sensitive credentials; Git ignores them.

\`\`\`powershell
cd C:\NEXUS_AGENT_TEST
python -m pip install "telethon>=1.36,<2"
$env:NEXUS_COLLECTOR_API_ID = [Environment]::GetEnvironmentVariable("NEXUS_COLLECTOR_API_ID","User")
$env:NEXUS_COLLECTOR_API_HASH = [Environment]::GetEnvironmentVariable("NEXUS_COLLECTOR_API_HASH","User")
python -m app.agent_system.channel_collector --login
python -m app.agent_system.channel_collector --once
python -m app.agent_system.channel_auditor --summary
\`\`\`

For recurring checks every 180 seconds, keep one separate process alive:

\`\`\`powershell
python -u -m app.agent_system.channel_collector --interval 180
\`\`\`

The bot's runtime remains separate and unchanged. Do not run collectors under
Production or commit their SQLite/session files.

## Access and verification

This collector only reads channels the authorized Telegram account can access.
Some public usernames may be renamed, unavailable, blocked, or require joining.
A failed access is logged by username/type; it must not be silently treated as
zero signals. Do not auto-join, bypass restrictions, or fabricate missing messages.

Only text posts with message ID and Telegram post time are imported. Edits, deletions,
captions and forwarded-source attribution need later work before robust scoring.
Old message history defaults to last 100 posts **per channel** on the first pass;
this is not a complete 60-day backtest. Non-text/image-only posts are not parsed.
The parser is deliberately provisional. No win rates or consensus signals are claimed.

A known limitation of V1 is that backfill and incremental ingest use maximum stored
message ID; older uncollected messages require explicit backfill tooling in V2.
