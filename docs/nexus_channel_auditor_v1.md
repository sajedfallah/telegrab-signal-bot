# NEXUS Channel Auditor V1 — isolated offline baseline

This prototype is **not** connected to Telegram user sessions, the production bot,
the NEXUS signal watcher, AutoTrade or live MT5 orders.

## Candidate list

The 20 public usernames are in app/agent_system/channel_auditor.py.
Presence on this list means research candidate only. It is **not** an
endorsement and does not establish current activity, ownership, accuracy,
trustworthiness, or permission to access private content.

## Input contract

Import externally obtained, lawfully accessible Telegram channel messages as JSON Lines:

\`\`\`json
{"channel":"ssfgold","message_id":123,"posted_at":"2026-10-14T10:00:00Z","text":"XAUUSD SELL 4142 SL 4146 TP1 4134"}
\`\`\`

Each line MUST include a real source channel username, Telegram message ID,
original post time with timezone and original text. Example above is synthetic
test data, **not** a verified historic signal.

Do not fabricate message IDs or reconstruct deleted/edited posts as original posts.
Store access keys outside the repository. Do not ingest private channel messages
without authorization.

## Run — Windows isolated test clone

\`\`\`powershell
cd C:\NEXUS_AGENT_TEST
python -m pytest tests/test_agent_channel_auditor.py -q
python -m app.agent_system.channel_auditor --import-jsonl data\channel_audit\messages.jsonl --summary
\`\`\`

SQLite destination: data/channel_audit/channel_audit.db (development only).
Back it up independently and exclude from Git commits.

## Current interpretation

- CANDIDATE: parseable direction, entry, SL and TP with basic ordering checks.
- REJECT: structurally invalid or conflicting values.
- INCOMPLETE: missing entry, SL or TP.
- NOT_SIGNAL: no gold reference or trade side.
- verified_win_rate and profit_factor are intentionally null.

Parsing alone does not validate posted-at tradability, fills, amendments, spreads,
slippage, stop-first ambiguity or results. NO CONSENSUS SIGNALS may be published
on the basis of this parser.

## Next milestones

1. Read-only authorized Telegram ingestion, using user-authorized access and
   provider rate limits. Capture origin, edits and subsequent management messages.
2. Expand parser for entry-zone, multi-target, reply-linked amendments and image-only
   posts marked as unparsed rather than invented.
3. Historical MT5 replay at message creation time; no lookahead. Score coverage,
   plausibility, duplication and closed-trade outcomes.
4. Detect copied signals and correlated channels before any weighted consensus.
5. Shadow-only independent ICT confirmation and hard-risk gates.

All historical win rates must come from reproducible trade-by-trade evaluation,
not self-reported outcomes or follower counts.
