# Runbook عملیاتی NEXUS ICT V22.31 — NEXUS_TRAIL_07

این فایل به‌عنوان صفحه Wiki/Runbook قابل استفاده است و روی استقرار، تست، مانیتورینگ، Incident و Rollback تمرکز دارد.

## وضعیت انتشار

- Expert: `NEXUS ICT V22.31`
- Profile: `NEXUS_TRAIL_07 / NEXUS Smart Hybrid v2`
- Tracking: Issue #47
- Backend/API migration: ندارد
- Database migration: ندارد
- Dependency migration: ندارد
- MetaEditor compile evidence: هنوز باید روی Windows/MT5 ثبت شود

## مدل رفتاری خلاصه

1. Entry با SL اولیه.
2. در `1R`، SL به Entry منتقل می‌شود.
3. در TP1، 30% از حجم اولیه بسته می‌شود؛ فقط پس از تأیید واقعی Volume.
4. بعد از TP1 تأییدشده، Structure 2/2 و ATR14×2 می‌توانند SL را فقط در جهت بهتر حرکت دهند.
5. در TP2، 30% دیگر از حجم اولیه بسته می‌شود.
6. Remaining Volume به‌عنوان Runner باقی می‌ماند.
7. در TP3/Final Target، کل Remaining Volume بسته می‌شود.

## Pre-Deployment Checklist

- [ ] نسخه قبلی MQ5/EX5 محفوظ است.
- [ ] فایل preset قبلی محفوظ است.
- [ ] Position باز روی حساب Production بررسی شده است.
- [ ] `SYMBOL_VOLUME_MIN` مشخص است.
- [ ] `SYMBOL_VOLUME_STEP` مشخص است.
- [ ] Broker Stops Level و Freeze Level بررسی شده‌اند.
- [ ] EA ابتدا روی Demo نصب می‌شود.
- [ ] Algo Trading روی Demo فعال است.
- [ ] AutoTrade فقط بعد از بررسی Initialization Log روشن می‌شود.

## Compile Gate

در MetaEditor:

1. فایل `NEXUS_ICT_V22_31_NEXUS_TRAIL_07_OWNER.mq5` را باز کنید.
2. Includeهای لازم را در مسیر صحیح قرار دهید.
3. Compile کنید.
4. نتیجه را در Release Evidence ثبت کنید.

Gate مطلوب:

`0 errors / 0 warnings`

تا زمانی که این خروجی ثبت نشده، نسخه Compile-verified محسوب نمی‌شود.

## Demo Test Matrix

### Test A — حجم 0.10، step 0.01

انتظار:

- TP1: `0.03` close
- TP2: `0.03` close
- Remaining: حدود `0.04`
- Final TP: close all remaining

### Test B — حجم 0.04، step 0.01

30% خام = `0.012`، حجم قابل اجرا باید به `0.01` نرمال شود.

### Test C — حجم 0.03، step 0.01

30% خام = `0.009` و Partial معتبر نیست.

انتظار:

- Stage به‌اشتباه Done نشود.
- Journal retry نمایش دهد.
- Backoff: `1,2,4,8,16,30...` ثانیه.

### Test D — Break Even

در 1R:

- requested SL = Entry;
- SL نباید عقب‌تر از Stop فعلی برود؛
- Broker Stops/Freeze validation باید رعایت شود.

### Test E — Hybrid runner

بعد از TP1:

- latest confirmed 2/2 structure بررسی شود؛
- ATR(14)[closed bar]×2 بررسی شود؛
- فقط stop بهتر اعمال شود؛
- هیچ SL regression پذیرفته نشود.

### Test F — Restart Recovery

1. Position را تا بعد از TP1 ببرید.
2. MT5 را Restart کنید.
3. EA را دوباره Load کنید.
4. TP1 نباید دوباره Partial شود.
5. Runner باید مدیریت را ادامه دهد.

### Test G — BUY / SELL symmetry

هم مسیر BUY و هم SELL باید تست شوند؛ فقط جهت Better Stop متفاوت است.

## Production Rollout

1. یک maintenance window کوتاه انتخاب کنید.
2. قبل از تغییر EA، new-entry را متوقف کنید.
3. Positionهای باز را ثبت کنید.
4. اگر Position قدیمی V22.30 باز است، از تبدیل mid-trade خودداری کنید.
5. EX5 کامپایل‌شده V22.31 را جایگزین کنید.
6. `InpUseNexusTrail07=true` را تأیید کنید.
7. Initialization Journal را بررسی کنید.
8. AutoTrade را فعال کنید.
9. اولین Lifecycle را Live Monitor کنید.
10. V22.30 rollback artifact را نگه دارید.

## Monitoring

Journal markers مهم:

- `[NEXUS][TRAIL07][TP1]`
- `[NEXUS][TRAIL07][TP2]`
- `[NEXUS][TRAIL07][FINAL]`
- `[NEXUS][TRAIL07][PARTIAL_RETRY]`

در اولین معامله Production موارد زیر ثبت شود:

- Ticket / Position ID
- Symbol / TF
- Initial volume
- Entry / Initial SL
- TP1 / TP2 / TP3
- SL در 1R
- Volume بعد TP1
- Volume بعد TP2
- Final close result

## Incident Playbook

### Partial Close اجرا نشد

بررسی کنید:

1. min volume؛
2. volume step؛
3. remaining volume validity؛
4. market state؛
5. broker retcode؛
6. retry timer.

Stage را به‌صورت دستی Done فرض نکنید مگر Volume واقعاً کم شده باشد.

### SL حرکت نکرد

بررسی کنید:

1. آیا 1R یا TP1 trigger شده؟
2. آیا candidate واقعاً بهتر از SL فعلی است؟
3. Stops Level/Freeze Level؛
4. Bid/Ask current؛
5. Modify retcode و terminal state.

### SL بیش از حد نزدیک شد

بررسی کنید:

1. Structure candidate؛
2. ATR value؛
3. broker clamp؛
4. اینکه candidate از closed bar آمده باشد؛
5. هیچ Instance دوم همان Position را مدیریت نکند.

### TP دوباره اجرا شد بعد Restart

بررسی کنید:

- `D1/D2/D3` Global Variables؛
- `TRAIL_MODE` و `TRAIL_VER` snapshot؛
- OWNER_TF / OWNER_INST state؛
- Position identifier consistency.

## Rollback

1. New entries را خاموش کنید.
2. Position فعال V22.31 را بدون بررسی Lifecycle به V22.30 واگذار نکنید.
3. در صورت امکان Position را با همان نسخه‌ای که باز کرده تا پایان مدیریت کنید.
4. EA را Remove کنید.
5. V22.30 EX5 و preset قبلی را Restore کنید.
6. Journal و Ownership state را بررسی کنید.
7. AutoTrade را فقط بعد از Verify مجدد فعال کنید.

## Security / Secrets

در Log یا Screenshot به Issue/PR عمومی اضافه نکنید:

- License key
- Admin token
- Exchange credential/key
- `.env`
- اطلاعات محرمانه حساب

## Evidence Required Before Release Sign-Off

- [ ] MetaEditor compiler output
- [ ] Demo BUY full lifecycle
- [ ] Demo SELL full lifecycle
- [ ] 0.10 lot partial distribution
- [ ] small-volume rejection/retry
- [ ] Restart recovery
- [ ] Stops/Freeze validation
- [ ] Multi-instance ownership test
- [ ] Rollback test or documented rollback dry-run

## Escalation Package

برای گزارش باگ، این موارد را ضمیمه کنید:

- Version: V22.31
- Broker/server
- Account type: Demo/Real + Hedging/Netting
- Symbol/TF
- Ticket/Position ID
- min/step/stops/freeze
- Initial and current volume
- Entry/SL/TP values
- Timestamp
- Journal excerpt بدون secrets
- Screenshot در صورت نیاز
