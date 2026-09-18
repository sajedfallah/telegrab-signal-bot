# NEXUS ICT V22.43 — Analytics Viewer + Persian RTL

## هدف
V22.43 ادامه‌ی مسیر Observability/Analytics است و **هیچ فیلتر جدیدی برای صدور Signal اضافه نمی‌کند**.

## تغییرات
- Analytics Viewer محلی برای CSVهای NEXUS.
- گزارش هفتگی خودکار از داده‌های واقعی ثبت‌شده.
- Telegram Signal / Position / Update / Close / Reject / Daily / Weekly به فارسی.
- اعمال RLM (U+200F) برای RTL پایدار در Telegram.
- اعداد قیمت و اصطلاحات فنی ضروری مثل FVG/CE/MFE/MAE/R حفظ می‌شوند.
- Daily CE / CE50 / CE75 analytics، Reversal/Continuation و MFE/MAE حفظ شده‌اند.
- Weekly analytics bucket بر مبنای هفته‌ی نیویورک اضافه شده است.

## گزارش هفتگی
پیش‌فرض:
- روز: Friday / day_of_week=5
- ساعت: 23:50 New York
- قابل تغییر از Inputs.

گزارش:
- Evaluated / Armed / Invalidated / Expired / Confirmed
- A+ / B
- Executed / Rejected
- Closed trades
- Win Rate
- Net P/L / Net R
- Avg MFE / MAE
- CE vs No-CE
- CE50 vs CE75
- Reversal vs Continuation

## Analytics Viewer
Viewer از فایل‌های Common Files متاتریدر استفاده می‌کند:
- SIGNAL_SNAPSHOTS
- LIFECYCLE_EVENTS
- TRADE_ANALYTICS
- TELEGRAM_DELIVERY

نمایش:
- KPIها
- CE attribution
- setup-class attribution
- expectancy by New York hour
- reject reasons
- Telegram delivery health
- latest signals/trades

## امنیت
Private MQ5 Server Build شامل credentialهای runtime است و نباید در repository عمومی commit شود.
این repository فقط specification/release docs را نگه می‌دارد.

## QA
- Static source checks: PASS
- MetaEditor compile: هنوز باید روی محیط MT5 انجام شود.
- Demo forward-test: قبل از Production الزامی است.
