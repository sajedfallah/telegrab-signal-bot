# Security Policy / Operational Security

## Secrets

Never commit or upload to the repository:

- `.env`
- Telegram bot tokens
- private API keys
- live database files
- runtime logs containing sensitive user/payment data
- backups
- local virtual environments

The repository contains `.env.example` with placeholders only.

If a real bot token is ever shared with an external service, pasted into a public issue, committed, or included in a distributable archive, treat it as compromised and rotate it through BotFather.

## Payment data

NEXUS currently supports manual Rial receipt approval and optionally USDT. Treat payment records and identifiers as sensitive business data.

Rules:

- SQL queries should remain parameterized.
- Discount/points/payment reservation logic must not be bypassed.
- USDT TXIDs must not be reusable.
- Approval/rejection must preserve an audit trail.

## Telegram access

- Admin authorization is Telegram-ID based.
- VIP channel links should remain user/license-specific and revocable.
- Entitlement checks must precede gated access.
- `protect_content` may be used for protected signal posts, but it cannot guarantee prevention of screenshots on all Telegram clients/devices.

## Repository visibility

This repository may be public. Do not assume a file is safe merely because the repository was initially empty/private in another environment.

## Responsible change policy

High-risk changes include:

- payment approval
- license activation/expiration
- DB migrations
- signal publication/result state
- Telegram channel membership/join requests

Require regression tests and review for these changes.
