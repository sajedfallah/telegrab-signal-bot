# NEXUS Testing Contract

Tests must target the canonical runtime paths described in `ARCHITECTURE.md`.

## CI-discovered commands

Current workflows explicitly run:

```bash
python -m compileall -q app run.py run_api.py
python -m compileall -q app run_api.py
python -m pytest tests/test_miniapp_api.py -q
python -m pytest tests/test_signal_agent_market_data_a.py tests/test_signal_agent_ict_event_b.py tests/test_signal_agent_context_c.py -q
python -m pytest tests/test_agentic_content_mvp.py tests/test_free_signal_topic_routing.py tests/test_customer_experience.py tests/test_telegram_admin_user_actions.py -q
```

There is no repository `package.json`, so no npm build/test command is part of the current contract. No `pyproject.toml` was present in the audited baseline, so lint/type-check commands must not be invented.

## Regression matrix

| Flow | Primary evidence |
| --- | --- |
| Telegram bot/admin actions | `tests/test_telegram_admin_user_actions.py`, routing tests |
| Mini App API | `tests/test_miniapp_api.py`, `tests/test_admin_miniapp_connectivity.py` |
| Signal Agent | `tests/test_signal_agent_market_data_a.py`, `test_signal_agent_ict_event_b.py`, `test_signal_agent_context_c.py` |
| Signal lifecycle | `tests/test_v055_trade_lifecycle.py`, result-flow and hardening tests |
| MT5 execution contract | AutoTrade backend/API compatibility, signal authority, execution-truth tests |
| Database hardening | `tests/test_db_hardening.py` and feature-specific persistence tests |
| Static/frontend regressions | Mini App tests plus HTML/asset checks embedded in versioned regression tests |

## Status vocabulary

- PASS: command executed successfully on the audited revision.
- FAIL: command executed and failed.
- NOT AVAILABLE: repository has no such tool/configuration.
- NOT VERIFIED: expected validation could not be executed in the current environment.

A static source inspection is not a substitute for a runtime PASS.
