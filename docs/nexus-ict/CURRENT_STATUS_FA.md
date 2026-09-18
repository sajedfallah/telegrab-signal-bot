# NEXUS ICT — وضعیت جاری تا V22.46

**آخرین به‌روزرسانی:** 2026-09-18  
**وضعیت جاری:** Demo / Forward Test Candidate  
**نسخه مورد تست یک‌هفته‌ای:** `NEXUS ICT V22.46 — Deep Research Telemetry + Analytics Viewer`

> این سند Source of Truth تیم توسعه برای مسیر NEXUS ICT Expert است. اگر بین فایل‌های قدیمی یا شاخه‌های قبلی اختلافی وجود داشت، وضعیت این سند و `main` بعد از Merge مرجع هستند.

## مرز امنیتی

نسخه خصوصی MQ5 فعلی دارای تنظیمات runtime حساس Telegram است و **نباید** در GitHub عمومی Commit شود. Repository عمومی فقط مشخصات، Release Notes، QA plan، schema و handoff را نگه می‌دارد.

## اصل معماری فعلی

مسیر تصمیم‌گیری Signal:

`D1 Daily CE / Quadrant → H1 Context → M15 POI/Structure → M5 Trigger → Signal Quality → Execution Safety → Trail07`

قانون ثابت از V22.42 به بعد:

**Telemetry / Analytics جدید نباید به‌تنهایی Signal را Block کند.**  
هدف فعلی: `Observe → Record → Join → Analyze`

## تاریخچه تغییرات مهم

### V22.31 — NEXUS_TRAIL_07
- BE دقیق در 1R.
- TP1 = 30% حجم اولیه.
- TP2 = 30% حجم اولیه.
- Runner اسمی ≈40%.
- Structure 2/2 + ATR(14)×2 بعد از TP1 تأییدشده.
- SL فقط در جهت محافظتی حرکت می‌کند.
- Partial Close فقط بعد از تأیید واقعی Broker وارد Stage بعد می‌شود.
- Retry bounded exponential برای Partial Close.
- State روی Position snapshot می‌شود تا Restart امن باشد.

### V22.32 — Server AutoTrade Private
- AutoTrade پیش‌فرض ON برای Server Build.
- M5 به‌عنوان execution timeframe.
- H1/M15 به‌صورت داخلی برای Context.
- Telegram runtime خصوصی.
- Account lock پیش‌فرض آزاد (`InpAuthorizedAccount=0`).

### V22.33 — Dual Sizing
- `RISK_PERCENT`
- `FIXED_LOT`
- Fixed Lot در صورت عبور از Hard Risk Cap Reject می‌شود؛ silently shrink نمی‌شود.
- Post-fill risk overrun در Fixed Lot باعث Close امن Position می‌شود.

### V22.34 — Telegram Every Issued Signal
- هر Signal زنده و Confirmed قبل از Runtime Execution Gate در Telegram ثبت می‌شود.
- Signal ID در زمان صدور تخصیص می‌گیرد.
- Signal می‌تواند صادر شود حتی اگر Execution رد شود.

### V22.35–V22.37 — Telegram Professional Lifecycle
- قالب‌های Signal / Open / Update / Close.
- TP1 / TP2 / BE / Trail / SL/TP Update.
- Partial P/L دلاری.
- TG TEST و HTTP 200 confirmation.
- WebRequest troubleshooting.

### V22.38 — Performance Core
- کاهش فشار UI/chart.
- جلوگیری از محاسبات و redraw غیرضروری.
- هدف: Chart responsiveness و عدم Freeze.

### V22.39 — Phase 1 Signal Quality Core
- REVERSAL / CONTINUATION.
- Market Regime.
- Component Score.
- Daily CE / Quadrant وارد Score شد.
- Daily CE پیش‌فرض +15؛ Reversal داخل CE +5 اضافه.
- امکان Cap کردن A+ Reversal بدون Daily CE.
- Hard Gateهای اصلی همچنان مستقل از Bonus Score هستند.

### V22.40 — Phase 2 Signal Delivery Core
- Signal اصلی Parent Message.
- Reply chain برای Open / Reject / TP / Trail / Close.
- Telegram Parent Message ID persist می‌شود.
- Execution Reject Engine.
- Execution Quality جدا از Signal Quality.

### V22.41 — Phase 3 Intelligence & Analytics
- Result R.
- MFE / MAE.
- Performance Attribution.
- CE vs No-CE.
- CE50 vs CE75.
- Reversal vs Continuation.
- Daily Intelligence Review.
- Weightها خودکار تغییر نمی‌کنند.

### V22.42 — Observability Data Lake
- Signal Snapshot dataset.
- Lifecycle dataset.
- Telegram Delivery dataset.
- Evaluated / Armed / Invalidated / Expired / Confirmed funnel.
- Time context: Server / UTC / New York.
- Spread, Tick age, Ping, Broker/Account state.
- Candle / Volume / POI / FVG / OB / OTE telemetry.
- **هیچ Signal Filter جدیدی اضافه نشد.**

### V22.43 — Analytics Viewer + Persian RTL Telegram
- Analytics Viewer محلی.
- گزارش هفتگی.
- Telegram user-facing messages فارسی و RTL.
- CE / Execution / Timing / Management views.

### V22.44 — Compile Fix
- `g_executionSignalContext` بعد از تعریف کامل `SignalData` منتقل شد.
- خطاهای زنجیره‌ای reference/enum رفع شدند.

### V22.45 — FileWrite Fix
- رفع محدودیت تعداد پارامترهای `FileWrite`.
- Signal Snapshot CSV با CSV string writer + `FileWriteString` نوشته می‌شود.
- V22.45 روی MetaEditor توسط کاربر Compile و روی Demo Load شد.
- Telegram connectivity با HTTP 200 پس از تنظیم WebRequest تأیید شد.

### V22.46 — Deep Research Telemetry + Analytics Viewer
- CE origin candle metadata.
- CE25 / CE50 / CE75.
- Wick strength / age / touch count / penetration.
- Sweep → MSS → FVG → Signal sequence timing.
- Displacement strength و Sweep depth.
- PDH / PDL / Asia liquidity map.
- Volatility percentile.
- 1 / 3 / 5 / 10 / 20-bar post-signal horizons.
- Time-to-1R / 2R / SL.
- Path MFE / MAE.
- Counterfactual management:
  - Trail07 actual
  - Fixed TP 1R/2R/3R
  - BE@0.75R / 1R / 1.25R → 2R
- Analytics Viewer با الگوی UI Mosaic Lite / Cruip.
- Viewer به‌صورت کامل فارسی و RTL شده است.
- **هیچ فیلتر جدیدی برای صدور Signal اضافه نشده است.**

## دیتاست‌های اصلی V22.46

در MT5 Common Files:

- `NEXUS_V22_46_SIGNAL_SNAPSHOTS_<SYMBOL>_<TF>.csv`
- `NEXUS_V22_46_LIFECYCLE_EVENTS_<SYMBOL>_<TF>.csv`
- `NEXUS_V22_46_TELEGRAM_DELIVERY_<SYMBOL>_<TF>.csv`
- `NEXUS_V22_46_TRADE_ANALYTICS_<SYMBOL>_<TF>.csv`
- `NEXUS_V22_46_RESEARCH_FEATURES_<SYMBOL>_<TF>.csv`
- `NEXUS_V22_46_SIGNAL_HORIZONS_<SYMBOL>_<TF>.csv`
- `NEXUS_V22_46_COUNTERFACTUAL_<SYMBOL>_<TF>.csv`

## وضعیت QA فعلی

- V22.45 MetaEditor compile/load: **تأییدشده توسط کاربر**.
- Telegram WebRequest / TG TEST: **تأییدشده**.
- V22.46 static validation: **PASS**.
- V22.46 MetaEditor compile: **باید در شروع تست یک‌هفته‌ای ثبت شود**.
- V22.46 Forward Demo E2E: **در حال شروع**.
- Production/Live rollout: **فعلاً مجاز نیست**.

## تصمیم محصولی فعلی

تا پایان تست یک‌هفته‌ای:
- Signal Gate جدید اضافه نشود.
- Weightها تغییر نکنند.
- Trail07 تغییر نکند.
- CE weighting تغییر نکند.
- فقط Bug fix / telemetry integrity / UI-data correctness مجاز است.

پس از یک هفته، داده‌ها Review می‌شوند و سپس V22.47 آغاز می‌شود.

## قدم بعدی

**V22.47 — Research Validation & Insight Engine**

تمرکز:
- Feature Combination Analyzer.
- Score Calibration.
- Confidence / Minimum Sample rules.
- Signal Failure Classification.
- MFE/MAE optimization.
- Time-decay analysis.
- CE research matrix.
- Data Quality Guard.
- SQLite analytics store.
- Weekly Persian Insight Report.

V22.47 ابتدا فقط **Insight** تولید می‌کند و حق تغییر خودکار Signal Score/Weight/Gate را ندارد.
