# NEXUS v0.5.4 — نسخه نهایی Trailing Engine

## اصلاح اصلی
موتور Trailing اکنون Profile-Based است و 7 مدل موجود پروژه را پشتیبانی می‌کند:

1. NEXUS_TRAIL_01 — اسکالپینگ محافظه‌کارانه
2. NEXUS_TRAIL_02 — Step Profit Lock
3. NEXUS_TRAIL_03 — Dynamic ATR
4. NEXUS_TRAIL_04 — Market Structure
5. NEXUS_TRAIL_05 — VIP Runner
6. NEXUS_TRAIL_06 — Fast Scalping
7. NEXUS_TRAIL_07 — NEXUS Smart Hybrid

## معامله دستی MT5
برای ایمنی، مدیریت خودکار معاملات دستی به صورت پیش‌فرض خاموش است:

`InpManageManualTrades=false`

بعد از اینکه نسخه را روی Demo تست کردی، اگر می‌خواهی معاملات دستی هم مدیریت شوند:
- EA Properties → Inputs
- `InpManageManualTrades = true`
- `InpManualTrailingProfile = NEXUS_TRAIL_01` تا `NEXUS_TRAIL_07`

### منطق معامله دستی
ربات از خود پوزیشن MT5 می‌گیرد:
- Entry = POSITION_PRICE_OPEN
- Initial SL = SL موجود هنگام اولین شناسایی
- Final TP = TP موجود روی همان پوزیشن
- Initial Volume = حجم اولیه

برای Profileهای دارای Partial Close، TPهای داخلی به صورت Virtual Milestone محاسبه می‌شوند و Final TP بروکر تغییر نمی‌کند:
- Virtual TP1 = Entry ± 1R
- Virtual TP2 = Entry ± 2R
- فقط اگر این سطوح قبل از Final TP باشند.

## نکته مهم درباره حجم
Partial Close تابع `SYMBOL_VOLUME_MIN` و `SYMBOL_VOLUME_STEP` بروکر است.
اگر حجم معامله آن‌قدر کوچک باشد که درصد Partial به یک حجم معتبر تبدیل نشود، ربات نباید کل پوزیشن را به اشتباه ببندد؛ Partial در آن سطح انجام نمی‌شود.

مثال:
- حجم 0.01
- Step = 0.01
- نصف حجم = 0.005
- این حجم قابل معامله نیست؛ بنابراین نصف‌بستن واقعی در این حساب ممکن نیست.
برای Partial مطمئن، حجم باید متناسب با Volume Step انتخاب شود.

## Safety
- Manual position بدون SL مدیریت نمی‌شود.
- SL نامعتبر یا در سمت اشتباه Entry مدیریت نمی‌شود.
- Final TP دستی توسط Trailing Engine جابه‌جا نمی‌شود.
- Trailing فقط SL را جلو می‌برد و SL را به عقب برنمی‌گرداند.
- Stop Level و Freeze Level بروکر در محاسبه SL لحاظ می‌شوند.
- Manual management فقط با Opt-in صریح فعال می‌شود.

## تست
در محیط Python:
`python -m pytest -q`

نتیجه نسخه حاضر:
`75 passed, 3 skipped`

فایل MQ5:
`mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5`

قبل از استفاده روی Live، فایل MQ5 را در MetaEditor کامپایل کن و ابتدا روی Demo ePlanet-MT5 تست کن.
