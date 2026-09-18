# Changelog

این فایل از نسخه **NEXUS ICT Expert V22.31** به بعد، تغییرات Companion Expert را در کنار NEXUS CORE ثبت می‌کند. برای تاریخچه نسخه‌های قدیمی Core/AutoTrade به فایل‌های `NEXUS_V*.md`، `RELEASE_NOTES_*.md` و `README_FA.md` مراجعه کنید.

## [NEXUS ICT V22.42] — 2026-09-18

**نام انتشار:** `OBSERVABILITY DATA LAKE`  
**دامنه:** MT5 ICT Expert / Signal Observability / Analytics  
**Issue:** #50  
**Pull Request:** #48

### Added

- Deep Signal Snapshot telemetry برای ستاپ‌های Live ارزیابی‌شده و Signalهای Confirmed.
- Lifecycle Event dataset برای:
  - SIGNAL_CONFIRMED
  - EXECUTION_ATTEMPT
  - EXECUTION_REJECT
  - POSITION_OPENED
  - POSITION_UPDATE
  - TRADE_CLOSED
- Telegram Delivery telemetry برای SENT / RETRY / FAILED.
- Time context کامل:
  - Server
  - UTC
  - New York
  - weekday
  - hour/minute
  - configured session
  - signal age
- Runtime market context:
  - Bid/Ask
  - Spread
  - Spread/ATR
  - Tick age
  - Terminal ping
- Signal quality/context snapshot:
  - score / grade
  - component scores
  - REVERSAL / CONTINUATION
  - market regime
  - execution quality
- Daily CE telemetry:
  - CE active
  - CE50 / CE75
  - Entry distance to CE50/CE75 normalized by ATR
  - CE strength
- POI/FVG/OB/OTE measurements.
- Liquidity / ICT rule flags.
- Signal-candle body/wick/range normalized by ATR.
- Tick-volume ratio against configurable lookback.
- Account/broker runtime context.
- Evaluated / Armed / Invalidated / Expired / Confirmed funnel in daily intelligence review.

### Preserved

- Daily CE weighting from V22.39.
- Parent/reply Telegram lifecycle from V22.40.
- R/MFE/MAE and attribution from V22.41.
- Performance Core.
- AutoTrade / Dual Sizing.
- NEXUS_TRAIL_07.

### Important behavior boundary

**V22.42 هیچ Signal Filter یا Hard Gate جدیدی اضافه نمی‌کند.**

Telemetry جدید فقط برای:
`Observe → Record → Join → Analyze`

است و به‌صورت مستقیم Signal را Block نمی‌کند.

### Security

Private server MQ5 artifact دارای runtime credentials خصوصی است و در repository عمومی commit نمی‌شود.
Repository فقط release/spec/schema را نگه می‌دارد.

### QA

- Static source integrity: PASS
- SignalData reference validation: PASS
- Brace balance: PASS
- Telemetry hooks presence: PASS
- MetaEditor compile: هنوز باید ثبت شود
- Demo forward test: هنوز باید ثبت شود

### Related

- #50
- `docs/releases/NEXUS_ICT_V22_32_TO_V22_42_FA.md`
- `docs/analytics/NEXUS_ICT_V22_42_TELEMETRY_SCHEMA_FA.md`

## [NEXUS ICT V22.31] — 2026-09-17

**نام انتشار:** `NEXUS TRAIL 07`  
**دامنه:** MT5 ICT Expert / Position Management  
**NEXUS CORE Backend:** بدون تغییر  
**Issue:** #47  
**Pull Request:** #48

### Added

- پیاده‌سازی Profile رسمی `NEXUS_TRAIL_07` با نام **NEXUS Smart Hybrid v2** در Expert فعلی.
- ورودی `InpUseNexusTrail07=true` برای فعال‌سازی مدل جدید روی Positionهای جدید.
- Snapshot سطح Position برای مدل مدیریت:
  - `TRAIL_MODE=7`
  - `TRAIL_VER=2`
  - `TRAIL_BE_R=1.0`
  - `TRAIL_TP1_PCT=30`
  - `TRAIL_TP2_PCT=30`
  - `TRAIL_RUNNER_PCT=40`
- Break-even دقیق روی Entry در `1R` برای Trail 07.
- TP1: درخواست Partial Close معادل `30%` حجم اولیه immutable.
- TP2: درخواست Partial Close دوم معادل `30%` حجم اولیه immutable.
- Runner اسمی `40%` و بسته‌شدن کامل Remaining Volume در Final TP/TP3.
- Hybrid trailing بعد از تأیید واقعی TP1:
  - Market Structure با `swing_left=2` و `swing_right=2`.
  - ATR با `period=14` و `multiplier=2.0` روی کندل بسته‌شده.
  - انتخاب فقط Stop بهتر؛ SL هرگز عقب نمی‌رود.
- Retry/Backoff برای Partial Close ناموفق:
  - `1s → 2s → 4s → 8s → 16s → 30s → 30s ...`
- UI status برای نمایش `TRAIL NXS07` هنگام فعال بودن Profile 07.
- Cleanup کامل Global Variables مربوط به Trail07 پس از بسته‌شدن Position.

### Changed

- مدل Position Management پیش‌فرض از منطق V22.30 (`25/25/25 + runner`) به Profile رسمی NEXUS Trail 07 (`30/30/40`) برای Positionهای جدید تغییر کرد.
- شروع Runner Trail در Trail07 از «بعد TP3» به **بعد از TP1 تأییدشده** تغییر کرد تا با موتور رسمی NEXUS هم‌راستا باشد.
- در Trail07، Break-even offset قابل تنظیم V22.30 کنار گذاشته شد؛ Stop دقیقاً روی Entry قرار می‌گیرد.
- در Trail07، `EXIT FIXED / EXIT EMA / EXIT STRUCT` دیگر رفتار Position جدید را تغییر نمی‌دهد؛ Profile 07 منبع رفتار authoritative است.
- Final TP در Trail07 روی Broker نگه داشته می‌شود و در رسیدن به TP3 تمام حجم باقی‌مانده بسته می‌شود.
- Swing detector در مسیر Trail07 از طول پویا به Pivot ثابت `2/2` مطابق Profile رسمی تغییر کرد.
- ATR Trail در مسیر Trail07 به ATR(14)×2 روی closed bar تثبیت شد.

### Fixed / Hardened

- جلوگیری از ثبت کاذب `TP_DONE` وقتی Partial Close به علت `SYMBOL_VOLUME_MIN` یا `SYMBOL_VOLUME_STEP` قابل اجرا نیست.
- جلوگیری از ادامه Lifecycle صرفاً بر اساس درخواست داخلی EA؛ Stage فقط بعد از تأیید کاهش واقعی Volume جلو می‌رود.
- جلوگیری از عقب‌بردن SL توسط Structure یا ATR candidate.
- جلوگیری از پرش TP2 روی TP1 تأییدنشده؛ ترتیب قوی‌تر Expert حفظ شد:
  `TP1 confirmed → TP2 confirmed → Final TP`.
- جلوگیری از تکرار Partial پس از Restart با Persist شدن Stage state و Profile snapshot.
- حفظ Broker Stop Level و Freeze Level در Stop candidateها.

### Performance

- Trail07 حداکثر یک management pass در هر ثانیه برای هر Position انجام می‌دهد، مطابق الگوی موتور NEXUS و برای کاهش فشار Modify/Partial روی Trade Server.
- ATR از Handle موجود Expert و closed-bar value استفاده می‌کند؛ Handle جدید در هر Tick ساخته نمی‌شود.
- هیچ Query، Migration یا Worker جدید Backend برای این نسخه اضافه نشده است.

### Backend / API

**هیچ تغییر Backend یا API در V22.31 انجام نشده است.**

- AutoTrade API version موجود در Core همچنان `0.6.5` است.
- Contractهای Activation, License Check, Heartbeat, Signal Receipt, Command Receipt و MT5 Admin Signal بدون تغییر باقی مانده‌اند.
- هیچ endpoint جدید/حذف‌شده/Breaking API change برای این انتشار وجود ندارد.

### Database

- هیچ schema migration جدید وجود ندارد.
- هیچ جدول/ستون/ایندکس جدید برای V22.31 اضافه نشده است.
- State مربوط به Trail07 این Expert در MT5 Terminal Global Variables نگهداری می‌شود، نه SQLite Backend.

### Infrastructure / Deployment

- بدون تغییر در Windows Server topology.
- بدون تغییر در Uvicorn/FastAPI service configuration.
- بدون تغییر در Telegram Bot service.
- بدون تغییر در Docker/Kubernetes؛ این Release چیزی به containerization اضافه نمی‌کند.
- GitHub Actions موجود بدون تغییر است؛ MetaEditor compile هنوز خارج از CI انجام می‌شود.

### Dependencies

هیچ dependency Python یا MQL جدیدی اضافه نشده است. `requirements.txt` بدون تغییر است:

- `aiogram==3.29.1`
- `aiodns>=3.2,<4`
- `python-dotenv==1.0.1`
- `tzdata==2026.3`
- `Pillow==11.3.0`
- `arabic-reshaper>=3,<4`
- `python-bidi>=0.6,<1`
- `fastapi==0.128.2`
- `uvicorn==0.48.0`
- `httpx>=0.27,<1`
- `cryptography>=43,<47`
- `ccxt>=4.4,<5`

### Security

- هیچ credential جدیدی در Source ذخیره نشده است.
- License/Admin authentication Backend تغییر نکرده است.
- Trail07 فقط Positionهای متعلق به Instance/Ownership فعلی Expert را مدیریت می‌کند؛ Safetyهای `OWNER_TF / OWNER_INST / heartbeat` نسخه قبلی حفظ شده‌اند.
- AutoTrade در Expert همچنان باید صریحاً فعال شود و فعال‌بودن Algo Trading در MT5 الزامی است.

### Migration

برای مهاجرت از V22.30:

1. Positionهای باز V22.30 را قبل از تعویض نسخه ثبت/بررسی کنید.
2. از Profile و Inputs فعلی MT5 اسکرین‌شات یا preset بگیرید.
3. V22.31 را در MetaEditor Compile کنید.
4. ابتدا روی Demo نصب کنید.
5. `InpUseNexusTrail07=true` را تأیید کنید.
6. برای تست دقیق 30/30/40، حجم `0.10` با Broker step `0.01` پیشنهاد می‌شود.
7. رفتار 1R/TP1/TP2/TP3 و Restart recovery را Verify کنید.
8. فقط بعد از تأیید Demo، Rollout به VPS/حساب Production انجام شود.

> توصیه عملیاتی: Profile management برای Position در لحظه ایجاد Snapshot می‌شود؛ برای جلوگیری از ambiguity، Positionهای باز قدیمی را وسط Lifecycle به مدل جدید تبدیل نکنید.

### QA / Verification

Static integration checks انجام‌شده برای artifact V22.31:

- Version marker: PASS
- Profile enabled default: PASS
- BE 1R: PASS
- TP1 30%: PASS
- TP2 30%: PASS
- Runner 40%: PASS
- ATR14×2: PASS
- Swing 2/2: PASS
- Runner after confirmed TP1: PASS
- Sequential TP2 gate: PASS
- Final remaining-volume close: PASS
- Exponential backoff: PASS
- Execution-truth partial confirmation path: PASS
- Restart-safe management snapshot: PASS
- Brace balance/static source integrity: PASS

Volume-step examples با `min=0.01`, `step=0.01`:

- `0.10 → TP1 0.03, TP2 0.03, runner ≈ 0.04`
- `0.04 → 30%=0.012 → broker-normalized 0.01`
- `0.03 → 30%=0.009 → Partial نامعتبر؛ Stage باید Pending/Retry بماند`
- `0.01 → Partial 30% غیرممکن`

### Not Yet Verified

- MetaEditor compile با ادعای `0 errors / 0 warnings`: **هنوز ثبت نشده**.
- Forward Demo E2E با Broker واقعی: **هنوز ثبت نشده**.
- Live-account validation: **انجام نشده و قبل از Demo توصیه نمی‌شود**.
- Line/branch code coverage برای مسیر MQL5: **اندازه‌گیری نشده**.

### Related

- Issue #47 — مستندسازی و Release governance برای V22.31.
- PR #48 — مستندات release و runbook این نسخه.
- Source behavior reference: `app/autotrade/trailing_profiles.py` و `mt5/NEXUS_AutoTrade/Include/TrailingEngine.mqh`.
- Execution-truth reference: `mt5/NEXUS_AutoTrade/Include/TradeManager.mqh` و `tests/test_v063_trailing_execution_truth.py`.
