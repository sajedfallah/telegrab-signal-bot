# NEXUS Telegram Signal Bot — v7.0.0 Baseline

> **Repository baseline:** `NEXUS CORE v7.0.0`  
> This is the first version designated as suitable for real execution and ongoing development.

NEXUS is a Telegram-based subscription, signal publishing, reporting, referral, and license-management platform for Forex and Crypto communities. The bot is designed around a **Telegram-first operating model**: administrators create and manage signals, users purchase or receive access licenses, signals are distributed to FREE/VIP channels, live trade updates are chained as replies, results are recorded, and daily/weekly performance reports are generated automatically.

The project began as a VIP subscription bot and evolved into a signal-management platform. v7.0 is the first baseline intended to be maintained as a software product rather than as a sequence of ZIP patches.

## Current baseline

- **Version:** `7.0.0`
- **Runtime:** Python 3.11
- **Telegram framework:** aiogram 3.x
- **Primary database:** SQLite (`nexus_bot.db` at runtime)
- **Persistent FSM:** SQLite (`nexus_fsm.db` at runtime)
- **Timezone default:** `Asia/Tehran`
- **Deployment mode:** long polling
- **Target OS used during development/testing:** Windows 10/11
- **Secrets:** never committed; configure a local `.env`

## What NEXUS currently does

### Client experience

1. Language selection / language change (Persian or English).
2. Mandatory public-channel membership gate.
3. Main client navigation:
   - Analysis & Signal Channels
   - Buy Subscription
   - Account
   - Referral & Points
   - Support / Change Language
4. FREE signal channel access.
5. VIP access controlled by active license/entitlements.
6. Auto-Trade access entitlement prepared at the license layer; real Auto Trade execution is **not implemented yet**.
7. Rial receipt-payment flow with admin approve/reject.
8. USDT payment structure with TXID validation and anti-reuse logic when configured.
9. Referral and NEXUS Points.
10. Promo codes, campaign discounts, renewal discounts, and points-based discounts.
11. Secure VIP join-request links tied to the user/license.
12. Account view with active entitlement and paid purchase history including start/end dates.

### Signal Center

Administrators can create Forex or Crypto signals with:

- chart screenshot,
- predefined symbol menu or manual symbol,
- BUY/SELL or LONG/SHORT direction,
- entry,
- stop loss,
- **dynamic number of take profits** (not limited to TP1/TP2/TP3),
- Forex lot size,
- Crypto leverage,
- risk percentage,
- calculated R:R,
- a fixed NEXUS trailing profile,
- destination: FREE / VIP / BOTH.

Supported NEXUS trailing profiles:

- `NEXUS_TRAIL_01` — Safe Scalping
- `NEXUS_TRAIL_02` — Step Profit Lock
- `NEXUS_TRAIL_03` — Dynamic ATR
- `NEXUS_TRAIL_04` — Market Structure
- `NEXUS_TRAIL_05` — VIP Runner
- `NEXUS_TRAIL_06` — Fast Scalping
- `NEXUS_TRAIL_07` — NEXUS Smart Hybrid

A published signal is one framed chart image plus a compact text caption. Live updates are reply-chained to the latest message for that signal.

Supported live actions:

- Break Even
- Partial Close
- Trailing activation/update
- Update TP
- Update SL
- Close Signal
- Retry failed publication

On close, the bot asks for exit price and a final chart image. The final result is published in the same **single-photo + caption** format as the initial signal.

### Performance and reports

- Daily admin reports
- Weekly admin reports
- Daily/weekly compact channel reports
- FREE and VIP statistics are calculated separately and displayed together in public performance reports
- Signal Analytics Dashboard:
  - 7 days
  - 30 days
  - all time
  - symbol breakdown
  - trailing-model breakdown
  - FREE vs VIP comparison
  - win/loss/break-even
  - win rate
  - direction-aware return
  - Forex pips
  - Crypto percentage
  - average R:R

### Subscription / License Engine

Each subscription plan can own an entitlement snapshot including:

- VIP access
- Auto-Trade access
- renewal discount
- upgrade rank (reserved for continued upgrade UX)

Paid approval activates the plan's access on the user license. Admin-issued free licenses also grant access. Trial access is treated separately. Early renewal preserves unused remaining time.

### Administration

The admin panel includes grouped access to users, subscriptions/licenses, payments, plans/prices, referrals/loyalty, discounts, campaigns, broadcast, CRM/retention, reports, audits, backups, Auto-Trade waitlist and the Signal Center.

## Repository map

```text
.
├── app/
│   ├── main.py                     # stable legacy handlers/workers/publishing pipeline
│   ├── config.py                   # environment configuration
│   ├── db.py                       # schema, migrations, repositories/query layer
│   ├── states.py                   # FSM states
│   ├── ui.py                       # inline/reply keyboard builders
│   ├── routers/
│   │   ├── analytics.py            # analytics admin router
│   │   └── subscriptions.py        # plan entitlement/renewal router
│   ├── services/
│   │   ├── analytics_service.py    # analytics business logic
│   │   └── license_service.py      # entitlement/license business logic
│   ├── signals/
│   │   ├── calculator.py           # R:R, Forex pips, Crypto return
│   │   └── card_generator.py       # chart framing / NEXUS visual assets
│   ├── storage/
│   │   └── sqlite_storage.py       # persistent aiogram FSM storage
│   └── assets/nexus_logo.png
├── tests/                           # executable baseline regression tests
├── docs/                            # project/product/operations/roadmap handoff
├── AGENTS.md                        # instructions/context for AI coding agents
├── ARCHITECTURE_V7.md               # v7 architecture summary
├── CHANGELOG.md
├── SECURITY.md
├── .env.example
├── requirements.txt
└── run.py
```

## Install on Windows

```cmd
py -3.11 -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt --timeout 120 --retries 10
python run.py
```

Or:

```cmd
setup_windows.bat
start_windows.bat
```

Copy `.env.example` to `.env` and fill in real values locally. **Never commit `.env`.**

## Tests

```cmd
run_tests.bat
```

Or:

```cmd
python -m compileall -q app tests
python -m unittest discover -s tests -v
```

The v7.0 repository baseline passes **21/21 tests** in the build environment. See `BUILD_TEST_REPORT_V7_0.txt`.

## Documentation — start here

| Document | Purpose |
|---|---|
| [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md) | Product scope and current capabilities |
| [`docs/FUNCTIONAL_SPEC.md`](docs/FUNCTIONAL_SPEC.md) | Detailed user/admin/signal/payment behavior |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Runtime architecture, modules and data ownership |
| [`docs/PROJECT_HISTORY.md`](docs/PROJECT_HISTORY.md) | Evolution from early VIP bot to v7 baseline |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | Setup, production operations, backup and recovery notes |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Planned v7.1 → v10 development direction |
| [`docs/AI_HANDOFF.md`](docs/AI_HANDOFF.md) | Context/invariants for another AI or developer |
| [`SECURITY.md`](SECURITY.md) | Secrets, payment, access and security rules |
| [`AGENTS.md`](AGENTS.md) | Coding-agent operating rules |

## Deliberately not implemented yet

These are roadmap items, not missing accidental features:

- Vision AI/OCR-based automatic chart parsing
- real Auto Trade execution / MT5 bridge
- full Mini App dashboard
- online Iranian payment gateway
- PostgreSQL production migration
- webhook deployment

## Development principle

**Protect the stable Telegram core first.** New features should be implemented behind services/routers with migrations and tests. Avoid replacing working payment, license, signal, report or access flows without a regression test and a clear migration path.

---

Persian product documentation is available in `README_FA.md` and `README_V7_FA.md`.
