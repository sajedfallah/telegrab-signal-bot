# NEXUS ICT V22.47 — Research Validation & Insight Engine

این سند Scope نسخه بعدی بعد از پایان تست یک‌هفته‌ای V22.46 است.

## شرط شروع

V22.47 فقط بعد از Review دیتای Forward Test آغاز می‌شود.

## هدف

تبدیل دیتای V22.46 به Insight قابل اتکا، بدون Auto-Optimization و بدون تغییر خودکار Strategy.

## P0

### Feature Combination Analyzer
ترکیب‌هایی مانند:
- CE75 + First Touch + Sweep + MSS ≤ 2 bars + Fresh FVG.
- No-CE + Late MSS + Second Mitigation.
- Range Reversal + CE.
- Continuation + Trend/Expansion.

برای هر Combination:
- Samples
- Win Rate
- Expectancy R
- Avg/Median MFE
- Avg/Median MAE
- Max loss streak

### Score Calibration
Bucketهای Score باید با Outcome واقعی مقایسه شوند:
- 65–69
- 70–74
- 75–79
- 80–84
- 85–89
- 90+

هدف: بررسی monotonic بودن Score نسبت به Expectancy.

### Confidence Engine
Insight بدون Sample کافی نباید Strong معرفی شود.
Level پیشنهادی:
- LOW
- MEDIUM
- HIGH

Confidence باید Sample size، dispersion و data quality را لحاظ کند.

### Signal Failure Classification
Lossها به Failure Mode طبقه‌بندی شوند:
- Weak Sweep
- Late MSS
- Old CE
- Retested CE
- Deep Mitigation
- Weak displacement
- High spread/slippage
- Immediate adverse move
- Regime mismatch
- Unknown

### Data Quality Guard
- Duplicate Signal IDs
- Orphan trades
- Missing lifecycle
- Missing outcome
- Broken timestamp order
- Invalid R
- Missing research rows
- CSV schema mismatch

## P1

### MFE/MAE Optimization Lab
بررسی اینکه SL/TP فعلی نسبت به Distribution واقعی مناسب است یا خیر.

### Time Decay
Expectancy بر اساس تأخیر:
- Signal → Entry
- CE touch → Sweep
- Sweep → MSS
- MSS → Entry

### CE Research Matrix
- CE50 / CE75
- First / Second / Third touch
- CE age
- Wick strength
- Penetration %
- Reversal speed

### SQLite Analytics Store
CSV همچنان raw truth باقی بماند، اما Viewer برای Query/Join سریع داده را به `nexus_analytics.db` ingest کند.

## P2

### Weekly Insight Report
گزارش فارسی:
- قوی‌ترین Combination
- ضعیف‌ترین Combination
- CE edge status
- Score calibration warning
- Management comparison
- Data quality warning

## Safety Rule

در V22.47:
- Weight خودکار تغییر نمی‌کند.
- Gate خودکار اضافه نمی‌شود.
- Signal automatically disabled نمی‌شود.
- Insight فقط Recommendation است.

هر تغییر Strategy باید در PR جداگانه، با Evidence و Rollback plan انجام شود.
