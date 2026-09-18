## NEXUS Pull Request Checklist

### Scope
- [ ] Branch was created from the latest `main`.
- [ ] Scope is focused; unrelated historical branches were not merged wholesale.
- [ ] Production impact and rollback are described below when applicable.

### Validation
- [ ] Relevant local tests pass.
- [ ] Required GitHub Actions are green.
- [ ] Vercel Preview is `Ready` for Mini App/frontend changes.
- [ ] Authenticated Mini App changes were validated from Telegram with valid `initData`.
- [ ] No `.env`, token, credential, database, receipt, generated runtime file, or other secret is tracked.

### NEXUS production boundaries
- [ ] Backend / VPS impact reviewed.
- [ ] Telegram lifecycle impact reviewed.
- [ ] AutoTrade execution gating impact reviewed.
- [ ] MT5 / broker-truth impact reviewed.
- [ ] Gold/Forex data remains broker/MT5 sourced; no synthetic market truth was introduced.

### Preview / evidence
Vercel Preview URL or PR deployment status:

### Production impact
Describe affected runtime/services, or write `Frontend/docs only`.

### Rollback
Describe the revert / known-good deployment path, or write `Revert this PR`.
