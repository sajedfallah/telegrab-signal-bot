# NEXUS v0.5.8 — Final Hardening Changes

- AutoTrade fails closed: missing/invalid customer license can no longer silently fall back to STANDARD trading.
- Admin Token may be entered directly in the EA setup wizard; server-side account allow-list and token validation remain authoritative.
- Added compact tabbed MT5 status panel with Overview, Connection, Trading, Risk, Signal and System tabs plus minimize control.
- Telegram subscription buttons are compact: VIP, AutoTrade, VIP + AutoTrade.
- Pricing catalog synchronized to the approved USD/USDT prices.
- USDT payment example configuration uses TRC20 and the configured public wallet address.
- Added durable manual MT5 LIMIT order lifecycle: PENDING -> ACTIVATED using the same signal identity.
- Manual LIMIT creation is captured from MT5 order transactions; activation is correlated by the original pending order.
- Added PENDING trade-event support and order_type metadata to the MT5 bridge.
- Existing per-user AutoTrade execution/report records remain user-scoped.
- Existing idempotency and reconciliation mechanisms are preserved.

- Added an EX5 release gate so the stale pre-existing binary is never automatically delivered until the new v0.5.8 EX5 is compiled and explicitly released.
