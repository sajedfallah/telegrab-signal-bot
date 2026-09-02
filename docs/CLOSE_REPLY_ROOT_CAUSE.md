# NEXUS v0.6.5 — Closed Position Telegram Reply Root Cause and Verification

A broker-confirmed CLOSE could be reconciled before the queued CLOSE reached the Telegram worker. Reconciliation marked the signal `CLOSED` without Telegram publication; the queued CLOSE handler then returned early because the signal was already `CLOSED`. This could consume a durable event without publishing the channel result reply.

The P0 correction keeps undelivered broker close truth in retryable `CLOSING`, re-enqueues it through the durable MT5 event queue, and lets the ordinary CLOSE path own Telegram delivery and final `CLOSED`. Reconciliation is idempotent and does not requeue after a real CLOSE/MT5_CLOSE Telegram delivery exists.

The supplied deployment `.env` is tracked only on `fix/v065-close-reply-hardening` for the requested test period and has not been merged to `main`. With that configuration, Bot API identity, FREE/VIP channel resolution, administrator membership, `can_post_messages=True` on both signal channels, and Admin MT5 settings all passed. Secrets are not reproduced here.

GitHub Actions `Close Reply Hardening` run #8 on runtime code commit `1849a311e1aab9ece70e9e97c36ec93838cbc35e` passed: runtime env validation, live Telegram permission checks, Python compileall, 4 focused CLOSE/reconciliation tests, and the full 230-test Python suite. One unrelated third-party deprecation warning remains. Later commits only adjust CI/docs and do not change the verified runtime/CLOSE code.

The remaining production gate is a controlled Windows/MT5 demo close observing:

`MT5 CLOSE -> trade-event/history truth -> durable queue -> Telegram reply to original signal -> DB CLOSED`

Additional delivery hardening remains recommended for `destination=BOTH`: require every required channel to succeed before final `CLOSED`, and recover missing signal anchors per channel rather than only when both anchors are absent.
