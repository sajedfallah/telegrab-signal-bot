## Summary

<!-- What changed and why? -->

## Validation
- [ ] `python -m compileall -q app tests`
- [ ] `python -m pytest -q`
- [ ] Coverage reviewed for changed logic
- [ ] `python -m pip check`
- [ ] Black/Flake8 checked or legacy exceptions documented

## Safety
- [ ] No secrets, tokens, databases, logs, or runtime artifacts committed
- [ ] Database migrations are backward compatible
- [ ] Telegram/payment/license behavior has regression coverage where applicable
- [ ] MT5/AutoTrade changes include explicit lifecycle/error-path tests where applicable

## Documentation
- [ ] README/docs updated
- [ ] CHANGELOG updated
- [ ] Breaking changes called out

## Review notes

