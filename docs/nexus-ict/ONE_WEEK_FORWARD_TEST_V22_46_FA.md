# NEXUS ICT V22.46 — برنامه تست یک‌هفته‌ای Demo Forward

**بازه پیشنهادی:** 2026-09-18 تا 2026-09-25  
**محیط:** MT5 Demo / M5 execution  
**هدف:** جمع‌آوری داده واقعی بدون تغییر Strategy Rules.

## Freeze Rule

در این هفته هیچ Feature معاملاتی جدید اضافه نشود. فقط موارد زیر مجازند:
1. Compile/runtime bug fix.
2. Crash/freeze/performance fix.
3. Telemetry corruption / duplicate / missing-row fix.
4. Telegram delivery / RTL formatting fix.
5. Analytics Viewer data-read / UI bug fix.

هر تغییری که Signal eligibility، Score weight، CE bonus، Entry rule، SL/TP یا Trail07 را تغییر دهد باید تا پایان Review یک‌هفته‌ای متوقف بماند.

## Gate صفر — قبل از شروع

- [ ] V22.46 MetaEditor: 0 errors.
- [ ] Warningها Review شوند.
- [ ] Expert روی M5 Load شود.
- [ ] Algo Trading ON.
- [ ] TG TEST = HTTP 200.
- [ ] Common Files قابل نوشتن باشد.
- [ ] Analytics Viewer فایل‌ها را بخواند.
- [ ] حداقل یک restart test بدون error انجام شود.

## داده‌هایی که باید هر روز کنترل شوند

### Signal
- [ ] Evaluated setups
- [ ] Armed
- [ ] Invalidated
- [ ] Expired
- [ ] Confirmed
- [ ] A+ / B
- [ ] Reversal / Continuation
- [ ] Market Regime

### Daily CE / Quadrant
- [ ] CE active
- [ ] CE25/50/75
- [ ] First/Second/Third touch
- [ ] CE age
- [ ] Wick strength
- [ ] Entry penetration
- [ ] CE touch → Sweep time
- [ ] CE touch → Signal time

### Sequence
- [ ] Sweep depth
- [ ] Sweep → MSS
- [ ] MSS displacement
- [ ] MSS → Signal
- [ ] FVG size/fill
- [ ] FVG → Signal
- [ ] First mitigation

### Execution
- [ ] Signal Quality
- [ ] Execution Quality
- [ ] Planned Entry
- [ ] Actual Entry
- [ ] Spread
- [ ] Slippage
- [ ] Reject reason
- [ ] Broker-confirmed Position Open

### Position Management
- [ ] 1R / BE
- [ ] TP1 partial
- [ ] TP2 partial
- [ ] Trail updates
- [ ] Final close
- [ ] Result R
- [ ] MFE
- [ ] MAE

### Telegram
- [ ] Signal parent message
- [ ] Open reply
- [ ] Reject reply
- [ ] TP/BE/Trail replies
- [ ] Close reply
- [ ] فارسی و RTL
- [ ] Telegram SENT/RETRY/FAILED telemetry

## Dataset Integrity — روزانه

برای هر روز:
- [ ] CSV header ثابت است.
- [ ] Row شکسته یا malformed وجود ندارد.
- [ ] Signal ID duplicate غیرمجاز نداریم.
- [ ] Position Close بدون Signal linkage نداریم.
- [ ] Trade Analytics با Broker history سازگار است.
- [ ] Result R عدد منطقی است.
- [ ] MFE >= 0 و MAE >= 0.
- [ ] Horizon rows برای Signalهای قدیمی‌تر به‌تدریج پر می‌شوند.
- [ ] Counterfactual فقط برای Tradeهای بسته‌شده نوشته می‌شود.

## Evidence مورد نیاز تا پایان هفته

هدف اولیه:
- حداقل 5–10 Signal واقعی Demo.
- حداقل 3 Trade کامل Lifecycle.
- حداقل یک Execution Reject.
- حداقل یک Partial Close.
- حداقل یک Trail/BE event.
- حداقل یک Restart با Position باز.
- فایل‌های Research/Horizon/Counterfactual دارای Sample واقعی.

اگر تعداد Signal/Trade کمتر بود، Review انجام می‌شود اما نتیجه Statistical Edge قطعی اعلام نمی‌شود.

## Review نهایی — 2026-09-25

تحلیل اجباری:
1. CE vs No-CE.
2. CE50 vs CE75.
3. First Touch vs Retest.
4. Reversal vs Continuation.
5. Score calibration.
6. NY time/day expectancy.
7. Sweep → MSS timing.
8. Displacement strength.
9. FVG fill/age.
10. Spread/slippage vs outcome.
11. MFE/MAE distribution.
12. Trail07 vs Counterfactual.
13. Signal failure modes.
14. Data quality / missing linkage.

## معیار تصمیم برای V22.47

هیچ Feature صرفاً به‌دلیل Win Rate بالا تغییر نمی‌کند.

برای پیشنهاد تغییر باید حداقل این‌ها گزارش شوند:
- Sample size.
- Expectancy R.
- Win Rate.
- Avg/Median MFE.
- Avg/Median MAE.
- Loss streak.
- Confidence / data quality.
- مقایسه با Control group.

نتیجه تست باید در Issue tracking ثبت شود.
