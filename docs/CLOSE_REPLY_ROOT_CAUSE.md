# NEXUS v0.6.5 — Closed Position Telegram Reply Root Cause and Verification

## Root cause

A broker-confirmed CLOSE could be received through MT5 history reconciliation before the queued event-driven CLOSE reached the Telegram worker.

The old sequence was:

1. `reconcile_mt5_history()` matched the CLOSE.
2. The signal was changed to `CLOSED` without Telegram publication.
3. The queued CLOSE reached `_process_mt5_trade_event()`.
4. The handler returned immediately because the signal was already `CLOSED`.
5. The durable notification was marked sent even though no result reply had been published.

This created a silent, permanent loss of the Telegram close-result reply.

## P0 correction

The reconciliation path now separates broker truth from Telegram delivery finalization:

- broker-confirmed close facts remain durable;
- when no real Telegram CLOSE/MT5_CLOSE delivery exists, the signal is put into terminal/retryable `CLOSING` rather than silently finalized;
- the CLOSE is re-enqueued through the existing durable MT5 notification queue;
- the ordinary event-driven CLOSE path owns Telegram reply delivery and final `CLOSED` transition;
- repeated reconciliation is idempotent;
- once a real close reply message id exists, reconciliation does not create another close notification.

## Runtime configuration verification

Using the supplied deployment `.env` on the hardening branch:

- configuration import: PASS;
- Telegram Bot API identity: PASS;
- FREE destination resolves successfully: PASS;
- VIP destination resolves successfully: PASS;
- bot is administrator in FREE channel: PASS;
- bot has `can_post_messages=True` in FREE channel: PASS;
- bot is administrator in VIP channel: PASS;
- bot has `can_post_messages=True` in VIP channel: PASS;
- Admin MT5 allow-list and authentication configuration load successfully.

Secrets are intentionally not reproduced in this report.

## Automated verification

GitHub Actions `Close Reply Hardening` run #8 on commit `1849a311e1aab9ece70e9e97c36ec93838cbc35e`:

- runtime env validation: PASS;
- live Telegram channel permission diagnostic: PASS;
- `python -m compileall -q app tests scripts`: PASS;
- focused history/CLOSE reconciliation regression: `4 passed`;
- full Python suite: `230 passed` (one third-party deprecation warning only);
- workflow conclusion: SUCCESS.

## Remaining production E2E gate

Automated and live-permission verification is green. A controlled MT5 demo trade should still be opened and closed after deploying this branch so the actual chain is observed on the Windows runtime:

`MT5 CLOSE -> trade-event/history truth -> durable queue -> Telegram reply to original signal -> DB CLOSED`.

## Additional hardening still recommended

Two delivery-integrity improvements remain separate from the P0 root-cause correction:

1. For `destination=BOTH`, final `CLOSED` should require successful delivery to every required channel, not merely at least one channel.
2. Signal-anchor recovery should be evaluated per required channel; one existing anchor must not prevent recovery of a missing anchor in the other required channel.
