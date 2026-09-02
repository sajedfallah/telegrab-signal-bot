# Contributing to NEXUS

## Development environment

Use Python 3.11, create an isolated virtual environment, and install `requirements-dev.txt`.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

## Before opening a PR

Run:

```bash
python -m compileall -q app tests
python -m pytest -q --cov=app --cov-report=term-missing
python -m pip check
python -m black --check app tests
python -m flake8 app tests
```

## Coding standards

- Keep business logic independent from Telegram transport where practical.
- Prefer small services/repositories over expanding `app/main.py`.
- Preserve existing behavior unless a change is explicitly specified.
- Add a regression test for every bug fix and behavior change.
- Database migrations must be backward compatible and idempotent.
- Never log secrets, payment credentials, license keys, or bot tokens.
- Use type hints for new public functions and Google-style docstrings for new modules/classes/functions.

## Commits

Use imperative Conventional Commit-style messages, for example:

- `feat: add pending order lifecycle`
- `fix: preserve signal destination on fill`
- `docs: update deployment guide`
- `test: cover license renewal transaction`
- `chore: pin development dependencies`

Keep commits focused and independently reviewable.

## Review process

1. Open a PR with the supplied checklist.
2. Explain behavioral and migration impact.
3. Include test evidence.
4. Address review comments without weakening security or regression coverage.
5. Merge only after CI is green and the change is approved.
