# NEXUS Roadmap

The roadmap is ordered by **operational risk**, not by visual novelty.

## v7.1 — Production & Monitoring (next recommended release)

Goal: make v7 safe to run continuously with clear operational visibility.

Planned scope:

- end-to-end production regression checklist
- health checks for Telegram API, DB and background workers
- admin System Status page:
  - bot status
  - DB status
  - last backup
  - last daily report
  - last weekly report
  - pending payments
  - failed publications
- duplicate-instance prevention
- background queue for broadcast/reports/heavy jobs
- structured retry policy for transient Telegram errors
- more integration tests
- verified backup restore workflow
- off-host/encrypted backup option
- continued extraction of `main.py` into domain routers

## v8 — Mini App Dashboard

Mini App should not merely duplicate Telegram buttons. It should provide dashboard-heavy UX while Telegram remains the notification/action channel.

### Client Mini App

- current plan/license
- expiration date
- purchase/renewal
- payment history
- signal history
- performance/analytics
- FREE vs VIP reports
- NEXUS Points
- referral dashboard

### Admin Mini App

- sales dashboard
- users/licenses
- payment queue
- active signals
- performance analytics
- plan management
- reports

Suggested stack can be selected later; domain APIs should be designed before UI work.

## v9 — Vision AI Assisted Signal Creation

Goal: reduce manual signal-entry time while preserving admin control.

Possible workflow:

1. Admin uploads chart screenshot.
2. Vision layer suggests symbol / entry / SL / TP values.
3. Bot populates draft fields.
4. Admin reviews and edits.
5. **Explicit admin confirmation is mandatory before publication.**

Vision AI should assist, not autonomously publish financial signals.

## v10 — Auto Trade

Only after signal and license systems have sufficient real-world stability/history.

Expected components:

- MT5/execution bridge
- entitlement/license verification
- per-trade risk controls
- maximum daily loss
- maximum simultaneous positions
- symbol mapping
- broker-specific contract/pip settings
- trailing execution engine
- emergency stop / kill switch
- demo mode before live mode
- execution audit trail

## Additional medium-term opportunities

- PostgreSQL migration for larger-scale deployment
- Iranian online payment gateway instead of manual receipts
- webhooks instead of polling if deployment requires it
- price-feed integration for result verification
- plan upgrade/downgrade UX using `upgrade_rank`
- richer retention automations
- monthly referral competition/rewards

## Roadmap guardrails

Do not start a major roadmap phase until:

1. current production core has a stable rollback point,
2. migration is reversible or safely forward-compatible,
3. payment/license/signal regression tests pass,
4. no secrets are committed,
5. user-facing behavior is documented.
