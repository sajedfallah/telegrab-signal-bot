# NEXUS Project Overview

## Product definition

NEXUS is a Telegram-native operating system for a trading signal business. It combines five business domains in one bot:

1. **Acquisition** — public membership gate, referrals, campaigns and broadcasts.
2. **Monetization** — subscription plans, Rial/USDT payment flows, discounts and admin approvals.
3. **Access control** — time-bounded licenses, secure VIP join requests and entitlement checks.
4. **Signal operations** — signal creation, publication, live management, close/result and channel history.
5. **Performance/retention** — analytics, daily/weekly reports, CRM, reminders, points and renewal flows.

## v7.0 product baseline

v7.0 is the first repository version considered suitable as the canonical executable baseline. Earlier versions were iterative ZIP builds and patches. All future work should start from v7.0 or a descendant commit.

## User roles

### Client

A Telegram user who may be FREE, VIP, Auto-Trade-entitled, trial, expired, referred, or a paying customer.

### Administrator

A Telegram user whose Telegram ID exists in `ADMIN_IDS`. Admins should land directly in the admin panel on `/start` rather than first navigating through the client UI.

### Telegram channels

- Public/academy channel: mandatory membership gate.
- FREE signal channel: public signal distribution.
- VIP signal channel: paid/licensed signal distribution.
- Auto Trade channel/service: entitlement exists in v7, but the actual execution system is future scope.

## Core product rules

- User language is persistent and can be changed at any time.
- Admin and client text should not mix Persian and English inside the same language mode except immutable technical identifiers such as `XAUUSD` or `NEXUS_TRAIL_01`.
- Screens should be kept clean: transient FSM prompts/receipts should be removed where possible and a usable menu should remain at the bottom/end of the conversation.
- Payment records remain in the database even when chat messages are deleted.
- A VIP entitlement may come from a paid plan or an admin-issued license.
- The client VIP button must check entitlement; an entitled user should receive access, not be shown prices again.
- Signal publication is destination-aware: FREE, VIP, or BOTH.
- FREE and VIP message IDs are stored independently.
- Every live update belongs to a signal and is sent as a reply in each destination channel.
- Reply chaining should use the latest signal message/update in each channel.
- Signal close publishes a final chart frame + caption, not a second result image card.

## Current signal data model (conceptual)

A signal includes at least:

- internal ID / public code (`NX-....`)
- market (`FOREX` / `CRYPTO`)
- symbol
- direction
- entry
- stop loss
- dynamic take-profit list
- Forex lot size or Crypto leverage
- risk %
- risk:reward
- trailing profile
- destination
- status
- creator/admin
- original FREE/VIP message IDs
- last FREE/VIP message IDs
- timestamps
- close/exit/result values

Signal updates include action type, human description, changed values, admin, channel message IDs and creation time.

## Report philosophy

### Channel report

A compact performance card/caption for both FREE and VIP audiences. It should contain only useful trading statistics:

- total closed trades
- wins
- losses
- win rate
- profit/loss percentage

FREE and VIP sections are separate but shown together so both audiences can compare performance. Business-internal values such as revenue or user growth do not belong in a public channel report.

### Admin report

Admin reports may contain business metrics in addition to signal performance, but must stay vertical, grouped and readable.

## Visual identity

- NEXUS logo is in `app/assets/nexus_logo.png`.
- Chart framing should be a simple black frame with the logo and **no chart crop**.
- Signal and result posts use one chart-frame image plus caption.
- Avoid extra image cards and excessive emoji.

## Current constraints

- Telegram Bot API cannot guarantee prevention of screenshots on every client/device.
- `protect_content=True` can restrict forwarding/saving for protected posts, but is not a complete DRM system.
- Broker pip conventions for metals vary. v7 supports configurable pip sizes such as `XAUUSD_PIP_SIZE` and `XAGUSD_PIP_SIZE`.
- Auto Trade entitlement exists, but trade execution itself is not present.
