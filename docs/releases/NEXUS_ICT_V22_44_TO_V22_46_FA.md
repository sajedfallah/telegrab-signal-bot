# NEXUS ICT V22.44 → V22.46

## V22.44 — Compile Fix
- انتقال `g_executionSignalContext` به بعد از تعریف کامل `SignalData`.
- رفع خطاهای زنجیره‌ای reference/enum ناشی از ترتیب اعلان.

## V22.45 — FileWrite Fix
- جایگزینی FileWrite بسیار بزرگ Signal Snapshot با CSV string builder + FileWriteString.
- تطبیق 115 Header با 115 Value.
- حفظ Analytics Viewer، Telegram RTL، Weekly Report، Trail07 و AutoTrade.

## V22.46 — Deep Research Telemetry
اصل نسخه: **هیچ Signal Filter / Hard Gate جدیدی اضافه نشده است.**

### Research datasets
- `RESEARCH_FEATURES`
- `SIGNAL_HORIZONS`
- `COUNTERFACTUAL`

### Daily CE research
- D1 origin candle OHLC
- CE25 / CE50 / CE75
- wick type / wick size / D1 ATR strength
- zone age
- touch count / prior touches
- first/last touch
- entry wick penetration
- CE touch → Sweep / Signal timing

### Sequence research
- Sweep depth / ATR
- Sweep → MSS minutes/bars
- MSS displacement body/range / ATR
- Close beyond structure / ATR
- MSS → Signal
- FVG → Signal
- FVG size/fill
- first mitigation

### Liquidity / timing
- PDH / PDL
- Asia High / Low
- nearest liquidity and ATR distance
- New York time
- minutes from 09:30 NY
- minutes from configured window
- volatility percentile

### Post-signal path
- 1 / 3 / 5 / 10 / 20-bar return in R
- path MFE / MAE
- time to 1R / 2R / SL
- same-bar ambiguity flag

### Counterfactual management
- actual Trail07 R
- fixed TP 1R / 2R / 3R
- BE 0.75R → 2R
- BE 1.00R → 2R
- BE 1.25R → 2R

Counterfactual simulation is bar-based and conservative when target and stop can both be touched in the same candle.

### Security
Private MQ5 source is not committed because the server build contains runtime-sensitive Telegram configuration.

### QA
- static source checks: PASS
- SignalData member validation: PASS
- brace balance: PASS
- MetaEditor compile: required
- Demo forward test: required
