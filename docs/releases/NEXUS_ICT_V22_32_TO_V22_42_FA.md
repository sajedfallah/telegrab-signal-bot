# NEXUS ICT Expert — V22.32 تا V22.42

## وضعیت فعلی

Current companion Expert track: **V22.42 — Observability Data Lake**.

این مسیر توسعه از V22.32 تا V22.42 روی سه محور متمرکز شده است:

1. ایمنی و قابلیت اجرای AutoTrade.
2. کیفیت و Explainability سیگنال.
3. جمع‌آوری داده برای اندازه‌گیری Edge واقعی بدون اضافه‌کردن فیلترهای اضافی.

---

## V22.32 — Server AutoTrade Private

- AutoTrade پیش‌فرض ON برای Server deployment.
- Server M5 lock.
- Telegram private-server delivery.
- Position ownership / safety gates.
- NEXUS_TRAIL_07 integration preserved.

## V22.33 — Dual Sizing

دو مدل Position Sizing:

- Risk Percent
- Fixed Lot

Fixed Lot به‌صورت broker-normalized اجرا می‌شود و اگر Hard Risk Cap را نقض کند، Trade reject می‌شود؛ حجم به‌صورت پنهان کوچک نمی‌شود.

## V22.34 — Telegram for Every Issued Signal

Signal Confirmed قبل از Runtime Execution Gates به Telegram ارسال می‌شود.

نتیجه:
- Signal quality از execution result جدا می‌شود.
- AutoTrade rejection باعث گم‌شدن Signal نمی‌شود.

## V22.35–V22.37 — Telegram Lifecycle / Test

- Professional Telegram templates.
- Position update messages.
- TP/SL values in lifecycle updates.
- Realized partial P/L.
- Compile field correction.
- TG TEST button.
- HTTP 200 connection verification.

## V22.38 — Performance Core

هدف: جلوگیری از Chart freeze و UI lag.

- bounded history
- bounded signal visuals
- lighter SMC overlay
- UI priority window
- batched redraw
- shorter Telegram timeout
- New-bar-heavy signal processing
- trade/position management kept higher priority than visuals

## V22.39 — Phase 1 Signal Quality Core

### Standardized Signal Quality

- REVERSAL / CONTINUATION
- Market Regime:
  - TREND
  - RANGE
  - EXPANSION
  - COMPRESSION
  - HIGH VOLATILITY
- Component score:
  - HTF Context /20
  - Liquidity /20
  - Structure /20
  - POI /20
  - Timing /10
  - Environment /10
  - Daily CE bonus

### Daily CE / Quadrant

Daily CE در methodology این Expert به‌عنوان ناحیه مهم برگشت قیمت ثبت می‌شود.

Default model:
- Quadrant / Daily CE bonus: +15
- Reversal inside Daily CE: +5 additional
- CE50 / CE75 persisted for later attribution.

اختیاری:
- Reversal بدون Daily CE می‌تواند از A+ محدود شود، ولی این گزینه Default سخت‌گیرانه نیست.

## V22.40 — Phase 2 Signal Delivery Core

- Parent Signal Message
- Telegram reply lifecycle
- persisted parent message id
- POSITION OPENED
- EXECUTION NOT TAKEN
- TP1 / TP2 / BE / Trail updates
- TRADE CLOSED
- execution reject reason engine
- Execution Quality جدا از Signal Quality

## V22.41 — Phase 3 Intelligence & Analytics

### Trade attribution

در زمان Entry، Featureهای Signal Freeze می‌شوند و در Close با نتیجه Join می‌شوند.

Tracked:
- Daily CE
- CE50 / CE75
- FVG
- Mitigation
- OTE
- OB
- Killzone
- Reversal / Continuation
- Range / Trend
- Sweep
- MSS / CHoCH

### Result metrics

- Net P/L
- R multiple
- MFE in R
- MAE in R
- duration

### Observed edge reporting

- CE vs No-CE
- CE50-near vs CE75-near
- Reversal vs Continuation
- Range vs Trend/Expansion

وزن‌ها **خودکار تغییر نمی‌کنند**. سیستم فقط evidence جمع می‌کند.

## V22.42 — Observability Data Lake

V22.42 هیچ Signal Filter جدیدی اضافه نمی‌کند.

Architecture:

`Observe → Record → Join → Analyze`

### Dataset 1 — Signal Snapshots

File pattern:

`NEXUS_V22_42_SIGNAL_SNAPSHOTS_<SYMBOL>_<TF>.csv`

هر Signal / evaluated setup می‌تواند شامل موارد زیر باشد:

- Signal / setup identifiers
- Server / UTC / New York time
- NY weekday / hour / minute
- configured session label
- signal age
- Bid / Ask
- Spread
- Spread / ATR
- tick age
- terminal ping
- score / grade / class / regime
- component quality scores
- Daily CE / CE50 / CE75
- entry distance to CE50/CE75 in ATR
- POI / FVG / OB / OTE metrics
- liquidity metrics
- Sweep / MSS / mitigation / first mitigation
- macro / structure flags
- candle O/H/L/C
- candle body / wick / range normalized by ATR
- tick volume and volume ratio
- balance / equity / free margin / margin level
- leverage
- open strategy positions
- terminal/account trade permission
- connection state
- broker stop/freeze/volume constraints

### Dataset 2 — Lifecycle Events

File pattern:

`NEXUS_V22_42_LIFECYCLE_EVENTS_<SYMBOL>_<TF>.csv`

Events:
- SIGNAL_CONFIRMED
- EXECUTION_ATTEMPT
- EXECUTION_REJECT
- POSITION_OPENED
- POSITION_UPDATE
- TRADE_CLOSED

Runtime fields:
- price
- spread
- planned entry
- slippage
- volume
- closed volume
- SL / TP
- floating P/L
- realized delta
- MFE / MAE
- account state

### Dataset 3 — Telegram Delivery

File pattern:

`NEXUS_V22_42_TELEGRAM_DELIVERY_<SYMBOL>_<TF>.csv`

Tracks:
- SENT
- RETRY
- FAILED
- HTTP code
- signal id
- reply_to id
- message id
- retry count
- queue depth

### Negative examples

برای جلوگیری از Survivorship Bias فقط Signalهای موفق ثبت نمی‌شوند.

Live evaluated setup states:
- ARMED
- INVALIDATED
- EXPIRED
- CONFIRMED

نیز ثبت می‌شوند تا بعداً بتوانیم تفاوت Featureها را اندازه‌گیری کنیم.

---

## Signal quality boundary

V22.42 عمداً داده‌های بیشتر را به **Filter جدید** تبدیل نمی‌کند.

هدف این است که ابتدا Sample کافی جمع شود و سپس با Metricهایی مثل:
- Expectancy
- Win Rate
- Avg R
- MFE
- MAE
- sample size
- time-of-day
- spread bucket
- CE distance
- FVG fill
- volume ratio

اثر واقعی Featureها سنجیده شود.

---

## Security

Private server MQ5 builds شامل runtime credentials خصوصی هستند.

**Private MQ5 source نباید در repository عمومی commit شود.**

این PR فقط:
- behavior specification
- telemetry schema
- release documentation

را ثبت می‌کند و هیچ Bot Token / private credential را منتشر نمی‌کند.

## Backend / API / DB

تا V22.42:
- Core backend API migration اجباری برای این Expert track وجود ندارد.
- SQLite schema migration برای این تغییرات وجود ندارد.
- Telemetry فعلی local MT5 Common CSV + Terminal Global Variables است.
- External Market Context API هنوز به Signal gating متصل نشده است.

## QA

ثبت‌شده:
- static source integrity
- brace balance
- SignalData member validation
- preservation of AutoTrade / Dual Sizing / Trail07 / Performance Core
- telemetry hook presence

هنوز لازم:
- MetaEditor compile واقعی
- Demo E2E
- multi-symbol VPS soak test
- verification of CSV growth / retention policy
- production rollout approval

Related:
- #47
- #50
- PR #48
