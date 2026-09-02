# NEXUS v0.5.5 — MT5 Compile Fix

## اصلاحات
- تابع `SendManualOrClosedTradeEvent` از `void` به `bool` تغییر کرد تا همه مسیرهای خروجی مقدار معتبر برگردانند و خطاهای Compile مربوط به `function must return a value` حذف شوند.
- خطاهای خروجی این تابع به صورت `true/false` مدیریت می‌شوند.
- مقدار Manual Destination فقط پس از ارسال موفق Signal مصرف می‌شود؛ در خطای API مقصد حفظ می‌شود.
- هنگام اتصال موفق، Manual Destination از Global Variable حساب بارگذاری می‌شود.
- پنل `FREE / VIP / BOTH` بعد از اتصال موفق Admin یا License روی چارت نمایش داده می‌شود.
- خواندن حجم Screenshot با نوع `uint` برای جلوگیری از warning تبدیل `uint` به `int` اصلاح شد.

## تست
`python -m pytest -q` → **83 passed, 3 skipped**

## نکته Compile
این محیط لینوکس به MetaEditor/MetaTrader 5 دسترسی ندارد؛ بنابراین Compile نهایی MQL5 باید در MetaEditor ویندوز انجام شود.
