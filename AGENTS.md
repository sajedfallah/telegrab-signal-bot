# AGENTS.md — NEXUS coding-agent instructions

## Read before changing code

1. `README.md`
2. `docs/AI_HANDOFF.md`
3. `docs/FUNCTIONAL_SPEC.md`
4. `docs/ARCHITECTURE.md`
5. `docs/ROADMAP.md`
6. `SECURITY.md`

## Baseline

`NEXUS CORE v7.0.0` is the canonical first executable release.

## Coding rules

- Python 3.11 / aiogram 3.x.
- Preserve backward-compatible SQLite migrations.
- Keep secrets/runtime DBs out of git.
- Add tests for payment/license/signal changes.
- Prefer new routers/services over adding more unrelated logic to `app/main.py`.
- Do not perform a wholesale rewrite of stable flows.
- Keep Persian and English UX fully separated.
- Maintain single-photo signal/result publishing.
- Maintain dynamic TP support.
- Maintain per-channel message-ID/reply chaining.
- Maintain entitlement-based VIP/Auto-Trade access.

## Definition of done

A change is not done merely because a button exists. It must have:

- handler/router wiring
- validation
- persistence if needed
- error behavior
- tests
- documentation update
