# Development Guide

## Source of truth

`VERSION` is the canonical machine-readable release version. Keep release notes and compatibility metadata synchronized with it.

The repository currently preserves a historical v7 source snapshot under `.bootstrap/v7clean`; `docs/SOURCE_SNAPSHOT.md` defines its checksum and materialization workflow. The snapshot is a historical reference and should not be modified as part of ordinary feature work. citeturn93file0

## Module boundaries

The v7 architecture is deliberately hybrid. `app/main.py` remains the integration/orchestration layer; database access is concentrated in `app/db.py`; FSM declarations live in `app/states.py`; business services live under `app/services/`; Telegram routers live under `app/routers/`; calculation and signal-card logic lives under `app/signals/`; and persistent FSM storage lives under `app/storage/`. citeturn96file0

## Refactoring rules

1. Extract cohesive business logic into services rather than growing the legacy integration module.
2. Keep calculations deterministic and independent of Telegram transport.
3. Keep database mutations transactional and migration-safe.
4. Add regression coverage before changing lifecycle, payment, licensing or access behavior.
5. Prefer adapters for external providers so provider-specific code does not leak into domain logic.
6. Do not silently change public behavior during cleanup refactors.

## Documentation and docstrings

New public modules, classes and functions should use Google-style docstrings. Existing legacy code should be documented incrementally as it is touched; avoid a large mechanical rewrite that changes runtime behavior.

## Verification gate

A change is ready for review only after:

```bash
python -m compileall -q app tests
python -m pytest -q --cov=app --cov-report=term-missing
python -m pip check
python -m black --check app tests
python -m flake8 app tests
```

## Release checklist

- [ ] `VERSION` updated.
- [ ] `VERSION.txt` synchronized or explicitly retired.
- [ ] `CHANGELOG.md` updated.
- [ ] README/docs reflect actual behavior.
- [ ] Tests and coverage run.
- [ ] CI green.
- [ ] No secrets/runtime artifacts are tracked.
- [ ] Release tag is created from the reviewed commit.
