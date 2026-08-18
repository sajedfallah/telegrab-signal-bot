# Functional Specification — NEXUS v7.0

## 1. Startup and language

### Normal user

1. `/start`
2. Select Persian or English if no language is stored.
3. Verify mandatory public-channel membership.
4. Enter client main menu.

### Administrator

If Telegram user ID exists in `ADMIN_IDS`, `/start` should lead directly to the admin experience after required initialization/language behavior. The startup experience must not dump sample reports into the admin chat.

## 2. Client menu order

Canonical client main menu order:

1. **Analysis & Signal Channels**
2. **Buy Subscription**
3. **Account**
4. **Referral & Points**
5. **Support / Change Language**

### Analysis & Signal Channels

Contains:

- FREE Signal
- VIP Signal
- Signal + Auto Trade

FREE opens the FREE channel directly.

VIP checks license entitlement:

- active VIP entitlement → provide/refresh secure access link
- no entitlement → explain that a subscription is required and route to purchase

Signal + Auto Trade checks Auto-Trade entitlement in the same manner. The execution platform itself is future scope.

## 3. Subscription purchase

1. User opens Buy Subscription.
2. Active plans are listed with current prices.
3. The user selects a plan.
4. Applicable discounts may include:
   - renewal discount
   - promo code
   - campaign discount
   - NEXUS Points discount
5. User selects Rial or USDT when configured.
6. Payment record is created/reserved.
7. Admin approves or rejects.
8. On approval, license is activated/extended with a snapshot of plan entitlements.
9. User receives access instructions.
10. On rejection, reserved resources/discount use/points are released or refunded where applicable.

### Rial receipt UX

- Store user receipt message ID and temporary bot prompt IDs.
- After decision, delete receipt and temporary prompts best-effort.
- Remove the admin receipt card after decision where possible.
- Keep the persistent database history.

### USDT

USDT is disabled unless wallet/network/plan prices are configured. TXID is validated and duplicate use is rejected.

## 4. License behavior

License may be sourced from:

- paid plan
- admin-issued free entitlement
- trial

v7 plan entitlements include:

- VIP access
- Auto Trade access
- renewal discount
- upgrade rank placeholder

Early renewal extends the existing expiration instead of throwing away remaining days. Upgrading adds new entitlements while preserving remaining valid time.

## 5. Signal creation flow

Canonical creation sequence:

1. Create Signal
2. Market: Forex / Crypto
3. Upload chart image
4. Symbol selection
   - Forex default examples: XAUUSD, XAGUSD, EURUSD, GBPUSD, DOWJONES, NASDAQ
   - Crypto default examples: BTCUSD, SOLUSD, ETHUSD, BNBUSD
   - Manual symbol entry always available
5. Direction
6. Entry
7. Stop Loss
8. Number of Take Profits
9. TP values from TP1 through TPn
10. Forex: Lot Size / Crypto: Leverage
11. Risk %
12. NEXUS trailing profile
13. Destination: FREE / VIP / BOTH
14. Preview/confirmation
15. Publish

TP is dynamic. If admin defines 2 targets, only TP1 and TP2 are stored/displayed. If admin defines 10, TP1..TP10 are stored/displayed.

## 6. Signal publication format

Exactly one channel post per destination:

- framed chart image (full chart, no crop)
- concise caption

Caption starts with signal code such as `NX-0001`, not a redundant "NEXUS FOREX SIGNAL" heading.

Typical Forex caption fields:

```text
NX-0001
Symbol: XAUUSD
Direction: BUY

Entry: 4000
SL: 3950
TP1: 4050
TP2: 4100

Lot: 0.10
Risk: 1%
R:R: 1:2
Trailing: NEXUS_TRAIL_04 — Market Structure
```

In Persian mode, field labels should be Persian; immutable symbol/trailing identifiers remain unchanged.

Entry/SL/TP values should be easy to select/copy; Telegram code formatting is preferred over fake URL links.

## 7. Live signal management

### Break Even

Publish a short reply indicating SL moved to entry / risk removed. Update latest channel message IDs.

### Partial Close

Ask percentage and publish a short reply containing the closed percentage.

### Trailing

Publish trailing activation/management information and preserve the selected NEXUS trailing model.

### Update TP

Allow updates to any defined TP, including TP numbers above 3.

### Update SL

Ask for new stop-loss value, store it, and reply to the latest signal message.

### Retry publication

If one destination failed, retry the missing/failed destination without duplicating the destination that already succeeded.

## 8. Close / result

1. Admin clicks Close Signal.
2. Bot asks for final exit price.
3. Bot asks for final result/chart screenshot.
4. Direction-aware result is calculated.
5. Final result is posted as a reply to latest message in each relevant channel.
6. Result uses **one final framed chart image + caption** only.
7. Signal becomes closed only after meaningful result publication/storage succeeds.

### Result units

- Forex → Pips
- Crypto → Percentage

Direction matters:

- BUY/LONG profit: exit above entry
- SELL/SHORT profit: exit below entry

Forex pip-size defaults:

- common non-JPY pairs: typically `0.0001`
- JPY pairs: typically `0.01`
- metals: broker-specific, configured with environment values

## 9. Automated reports

### Schedule defaults

- Daily: 23:59 Asia/Tehran
- Weekly: Friday 23:59 Asia/Tehran

### Public channel report

Sent to both FREE and VIP channels when enabled. Contains two separate sections — FREE and VIP — with only:

- total trades
- wins
- losses
- win rate
- profit/loss %

### Admin reports

Admin-only reports may include broader business data, but must remain grouped and vertically readable.

## 10. Referral / loyalty

- Referral ownership is linked to Telegram users.
- Anti-self-referral rules apply.
- NEXUS Points can be awarded and used for discount according to configured rules.
- Referral leaderboard is available.

## 11. Admin plan management

Admin can create/edit/toggle plans and prices. v7 adds entitlement/renewal controls per plan. Runtime plan configuration should remain database-driven rather than requiring a code edit.

## 12. Chat cleanliness

NEXUS follows a "single dashboard/screen" UX where practical:

- edit existing bot screens rather than constantly sending new ones
- delete transient user/FSM messages best-effort
- keep main menu usable and near the bottom/end of chat
- broadcast/report messages should not permanently bury navigation
