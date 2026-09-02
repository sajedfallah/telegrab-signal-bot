# NEXUS Telegram Signal Bot

[![CI](https://github.com/sajedfallah/telegrab-signal-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/sajedfallah/telegrab-signal-bot/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)

NEXUS is a Telegram-first signal publishing and subscription platform. It provides administrator-controlled signal creation, FREE/VIP publication, payment and entitlement flows, reporting, analytics, referrals, and a license layer prepared for AutoTrade integration. The maintained repository baseline is currently the **7.0.x** line; `VERSION` is the canonical machine-readable version and currently reports `7.0.6`. citeturn91file0

> **Important:** The repository documentation describes AutoTrade as a prepared entitlement/integration layer; the historical v7 baseline explicitly states that real AutoTrade execution was not implemented in that baseline. Do not treat documentation as proof of live MT5 execution capability. citeturn88file0

## Features

- Persian/English Telegram UX.
- Public-channel membership gate.
- FREE and VIP signal publication.
- Signal Center with chart framing, dynamic take-profits, risk/reward calculations and destination routing.
- Signal lifecycle updates and reply chaining.
- Subscription, payment, entitlement and license management.
- Referral/points, discounts and campaigns.
- Daily/weekly reporting and signal analytics.
- Persistent SQLite business database and SQLite-backed FSM storage.
- Windows-oriented development scripts and a canonical v7 source snapshot.

The architecture is intentionally hybrid: stable legacy orchestration remains in `app/main.py`, while analytics, subscriptions, licensing and storage are extracted into services/routers. This is an incremental migration strategy rather than a wholesale rewrite. citeturn96file0

## Requirements

- Python **3.11**.
- Telegram Bot token created through BotFather.
- A Telegram admin ID and destination channel IDs.
- SQLite (bundled with Python).
- Network access to Telegram's Bot API.

The repository's canonical v7 documentation identifies Python 3.11, aiogram 3.x, SQLite and long polling as the baseline runtime choices. citeturn88file0

## Installation — Windows

```cmd
git clone https://github.com/sajedfallah/telegrab-signal-bot.git
cd telegrab-signal-bot
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copy the environment template:

```cmd
copy .env.example .env
```

Edit `.env` and provide real credentials and channel IDs. Never commit `.env`.

Start the bot using the repository's runtime entry point:

```cmd
python run.py
```

The historical baseline also documents `setup_windows.bat` and `start_windows.bat` where those scripts are present in the materialized source tree. citeturn93file0

## Configuration

`.env.example` documents the supported categories of configuration, including bot/channel identifiers, storage paths, timezone, payments, reports, AutoTrade API integration placeholders and XAU/XAG pip conventions.

Minimum values:

```dotenv
BOT_TOKEN=...
ADMIN_IDS=123456789
PUBLIC_CHANNEL_ID=-100...
FREE_CHANNEL_ID=-100...
VIP_CHANNEL_ID=-100...
TIMEZONE=Asia/Tehran
```

For AutoTrade-enabled deployments, configure the API base URL and a long random administrative secret. Keep private control APIs off the public Internet unless they are protected by appropriate transport and network controls.

## Repository layout

```text
.
├── app/
│   ├── main.py                 # Telegram integration/orchestration
│   ├── config.py               # environment/configuration
│   ├── db.py                   # SQLite schema, migrations and queries
│   ├── states.py               # canonical FSM states
│   ├── ui.py                   # keyboard/UI builders
│   ├── routers/                # extracted Telegram/admin routers
│   ├── services/               # business services
│   ├── signals/                # calculations and card generation
│   ├── storage/                # persistent FSM storage
│   └── assets/                 # branding/static assets
├── tests/                      # regression and unit tests
├── docs/                       # architecture, operations and product docs
├── scripts/                    # source/build utilities
├── .github/                    # CI and contribution templates
├── requirements.txt            # pinned runtime dependencies
├── requirements-dev.txt        # pinned test/lint dependencies
├── .env.example                # configuration template
├── CHANGELOG.md                # release history
├── SECURITY.md                 # security policy
├── CONTRIBUTING.md             # contribution workflow
├── LICENSE                     # MIT license
└── run.py                      # runtime entry point
```

The v7 source snapshot documentation records the canonical source paths and materialization process. citeturn93file0

## Testing

Install development dependencies:

```cmd
python -m pip install -r requirements-dev.txt
```

Run syntax compilation:

```cmd
python -m compileall -q app tests
```

Run tests and coverage:

```cmd
python -m pytest -q --cov=app --cov-report=term-missing --cov-report=xml
```

Run static checks:

```cmd
python -m black --check app tests
python -m flake8 app tests
python -m pip check
```

CI executes the same classes of checks through GitHub Actions.

## Troubleshooting

### `No module named pytest`

The virtual environment is active but the development dependencies are not installed:

```cmd
python -m pip install -r requirements-dev.txt
```

### `.venv\Scripts\activate` cannot be found

You are either in the wrong directory or `.venv` has not been created:

```cmd
cd /d "C:\path\to\telegrab-signal-bot"
py -3.11 -m venv .venv
.venv\Scripts\activate
```

### Telegram connection errors

Check outbound HTTPS connectivity, DNS, firewall/proxy rules, and that `BOT_TOKEN` is valid. Never paste the token into an issue or chat. A network failure is not evidence that the application code is incorrect.

### Bot starts but does not receive updates

Confirm the bot token, polling process, and Telegram privacy/channel permissions. Ensure only one polling process is using the same bot token in the test environment.

### Database problems

Stop the application before manual database maintenance. Back up `nexus_bot.db` and `nexus_fsm.db` before migrations or resets. Runtime databases are intentionally ignored by Git.

### Source snapshot materialization

The historical v7 repository contains a checksum-verified compressed source snapshot under `.bootstrap/v7clean`. Use `materialize_v7_source.bat` or `scripts/materialize_v7_source.py` as documented in `docs/SOURCE_SNAPSHOT.md`. citeturn93file0

## Security

- Never commit `.env`, bot tokens, admin tokens, payment credentials, databases or logs.
- Use unique long secrets for administrative APIs.
- Restrict AutoTrade/control endpoints to trusted networks.
- Do not expose SQLite runtime files or uploaded chart assets publicly.
- Do not put personal, payment or account credentials in GitHub issues.
- Report suspected vulnerabilities privately according to `SECURITY.md` rather than publishing exploit details.

## Documentation

- `docs/PROJECT_OVERVIEW.md` — product scope.
- `docs/FUNCTIONAL_SPEC.md` — user/admin behavior.
- `docs/ARCHITECTURE.md` — runtime architecture and responsibilities.
- `docs/OPERATIONS.md` — deployment and operations.
- `docs/ROADMAP.md` — planned development.
- `docs/SOURCE_SNAPSHOT.md` — canonical v7 snapshot and checksum.
- `SECURITY.md` — security policy.
- `CONTRIBUTING.md` — development and review process.

## Versioning and releases

Use Semantic Versioning (`MAJOR.MINOR.PATCH`) for releases. The existing repository has multiple historical version metadata files, so release work must keep `VERSION` and release documentation synchronized. The current `VERSION` file reports `7.0.6`. citeturn91file0

## License

MIT. See `LICENSE`.
