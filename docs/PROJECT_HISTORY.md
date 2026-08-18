# Project History / Evolution

This document explains how the current repository was reached. It preserves the architectural/product decisions that matter to future maintainers.

## Early VIP bot / v4-v5 lineage

The project started as a Telegram VIP subscription bot with:

- public-channel membership verification
- Persian/English UX
- Rial receipt payment
- admin approve/reject
- secure VIP access links/join requests
- timed subscriptions
- expiration reminders and automatic removal
- referral/NEXUS Points
- discounts/campaigns
- broadcast/CRM/backup/audit features

v5 became the stable business baseline but `main.py` remained heavily centralized.

## v6.0 — Core test baseline

The development focus shifted from subscription-only behavior to a broader NEXUS trading platform. A service-layer direction was adopted while keeping SQLite for local/early production testing.

## v6.1/v6.2 — Signal Center

The first Signal Center prototype exposed a button before all handlers were wired. That experience established an important project rule: **a UI button is not a feature until the full Telegram handler/database/channel path works**.

The Signal Center was then wired to:

- Forex/Crypto creation
- chart upload
- symbol/direction/entry/SL/TP
- FREE/VIP/BOTH destinations
- message-ID persistence
- live actions
- close/result

Several publication lifecycle bugs were fixed, including Telegram callback timeouts (`query is too old`) by acknowledging callbacks before long network operations.

## v6.3 — Automatic reports

Daily and weekly reporting was introduced with Asia/Tehran scheduling and idempotent dispatch tracking.

## v6.4 — Signal UX and lifecycle hardening

The signal presentation was simplified:

- full chart image kept intact
- simple black NEXUS frame
- information moved to caption
- redundant black information image removed
- dynamic TP count introduced
- signal code moved into the caption
- Break Even/close/result reply chain hardened
- final result changed to the same single-image + caption model

Additional stability/security work included SQLite WAL/busy timeout, stronger admin guards, safer membership-gate behavior, background broadcast improvements, normalized Persian/Arabic numbers and rotating logs.

## v6.5 — Client access/report UX

Client menu and entitlement behavior were redesigned around actual access:

- Analysis & Signal Channels
- Buy Subscription
- Account
- Referral & Points
- Support / Language

VIP and Auto Trade buttons now evaluate license entitlement instead of always showing plan prices. Public channel reports were simplified to compact FREE vs VIP performance summaries.

## v7.0 — Canonical repository baseline

v7.0 is the first version declared suitable as the maintained executable baseline.

Three major upgrades define v7:

1. **Signal Analytics Dashboard**
2. **Subscription/License Entitlement Engine**
3. **Persistent FSM + gradual modularization**

The project moves from "versioned ZIP patches" to a Git repository where future development should be made through commits/branches/PRs and documented migrations.
