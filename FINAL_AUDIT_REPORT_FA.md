# NEXUS v7.1.2 — Final Code Audit

## نتیجه بررسی

- Python syntax/compile: OK
- Automated tests available in the portable audit environment: **66 passed, 3 skipped**
- The 3 skipped tests require `aiogram`; the target Windows environment already installs `aiogram==3.29.1`, so they are expected to execute there.
- Static UI callback coverage: OK
- No synchronous `app.db` function is awaited from `app.main`.
- UTF-8 source files contain no UTF-8 BOM.
- AutoTrade source version: **0.5.0**

## اصلاحات نهایی

1. رفع خطای runtime در ثبت رسید پرداخت ریالی:
   `db.set_setting(...)` یک تابع synchronous است و دیگر با `await` فراخوانی نمی‌شود.
2. تست callbackهای UI مستقل از نوع quote تولیدشده توسط `ast.unparse` شده است.
3. `run_tests.bat` برای `.venv` استاندارد پروژه اصلاح شد.
4. پیام و راهنمای Compile برای MT5 با نسخه جاری **v0.5.0** همسان شد.
5. تست regression برای جلوگیری از بازگشت خطای `await` روی توابع synchronous دیتابیس اضافه شد.
6. تست regression برای همسانی نسخه AutoTrade با کد runtime اضافه شد.

## نکته استقرار

فایل `assets/autotrade/NEXUS_AutoTrade.ex5` در بسته فعلی وجود ندارد. این فایل باید با MetaEditor از سورس جاری `mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5` با نسخه 0.5.0 کامپایل و سپس در مسیر زیر قرار گیرد:

`assets/autotrade/NEXUS_AutoTrade.ex5`

سورس MQL5 برای مشتری ارسال نمی‌شود؛ ربات فقط EX5 کامپایل‌شده را تحویل می‌دهد.

همچنین `.env` واقعی عمداً در بسته نهایی قرار نگرفته و باید روی سیستم مقصد با مقادیر واقعی تنظیم شود.
