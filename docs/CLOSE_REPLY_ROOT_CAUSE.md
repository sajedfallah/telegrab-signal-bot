# NEXUS v0.6.5 — Closed Position Telegram Reply Root Cause and Verification

## Root cause

A broker-confirmed CLOSE could be received through MT5 history reconciliation before the queued event-driven CLOSE reached the Telegram worker. Reconciliation marked the signal `CLOSED` without Telegram publication; the queued CLOSE handler then returned early because the signal was already `CLOSED`, so the durable notification could be consumed without any channel result reply.

## P0 correction

The reconciliation path now separates broker truth from Telegram delivery finalization. An undelivered broker-confirmed close remains terminal/retryable as `CLOSING`, is re-enqueued through the durable MT5 event queue, and only the ordinary event-driven CLOSE path finalizes Telegram delivery and `CLOSED`. Repeated reconciliation is idempotent, and an already delivered CLOSE/MT5_CLOSE is not requeued.

## Runtime configuration verification

The supplied deployment `.env` is tracked only on `fix/v065-close-reply-hardening` for the requested test period; it has not been merged to `main`.

Using that configuration, configuration loading, Telegram Bot API identity, FREE/VIP target resolution, administrator membership, `can_post_messages=True` on both signal channels, and Admin MT5 configuration all passed. Secrets are intentionally not reproduced here.

## Automated verification

GitHub Actions `Close Reply Hardening` run #8 on runtime code commit `1849a311e1aab9ece70e9e97c36ec93838cbc35e` completed successfully:

- runtime env validation: PASS
- live Telegram channel permission diagnostic: PASS
- Python compileall: PASS
- focused CLOSE/history reconciliation tests: `4 passed`
- full Python suite: `230 passed`
- workflow conclusion: SUCCESS

One third-party deprecation warning remains; it is unrelated to the CLOSE reply path. Later commits only adjust CI/docs and do not change the tested runtime/CLOSE code.

## Remaining production E2E gate

A controlled Windows/MT5 demo close should still observe the complete runtime chain:

`MT5 CLOSE -> trade-event/history truth -> durable queue -> Telegram reply to original signal -> DB CLOSED`

## Additional delivery hardening

1. For `destination=BOTH`, final `CLOSED` should require successful delivery to every required channel.
2. Signal-anchor recovery should be evaluated per required channel so one existing anchor cannot mask a missing anchor in the other required channel.
