# NEXUS v7.1.0 — گزارش بررسی، تست و اصلاح

## نتیجه نهایی

- تست‌های Pytest قبل از اصلاح: 59 passed / 4 failed
- علت 4 شکست: تست‌های قدیمی هنوز نسخه MT5 را `0.4.5` انتظار داشتند، در حالی که سورس فعلی طبق `LATEST_VERSION.md` و changelog نسخه `0.5.0` است.
- اصلاح انجام‌شده: انتظار نسخه در 4 تست به `0.500` مطابق `#property version "0.500"` تغییر کرد.
- تست‌های Pytest بعد از اصلاح: **63 passed**
- `compileall`: **PASS**
- `validate_build.py`: **PASS**
- بررسی وجود سورس MT5 و فایل compile note: **PASS**
- بررسی secretهای واضح داخل سورس: موردی از Telegram Bot Token / Private Key / AWS key پیدا نشد.

## نکته مهم MT5

محیط فعلی Linux است و MetaEditor/MT5 در دسترس نیست؛ بنابراین کامپایل واقعی `.mq5 -> .ex5` در این محیط قابل انجام نیست.

سورس فعلی:
`mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5`

نسخه سورس:
`0.500` / `0.5.0`

برای Production باید همین سورس با MetaEditor در Windows کامپایل شود و EX5 حاصل با سورس فعلی هم‌نسخه باشد.

## تغییرات فایل‌های تست

فایل‌های اصلاح‌شده:
- `tests/test_autotrade_ex5_delivery.py`
- `tests/test_mt5_execution_diagnostics_static.py`
- `tests/test_mt5_license_input_paste_static.py`
- `tests/test_v709_payment_and_license_input.py`

این اصلاح فقط تست‌های stale را با نسخه واقعی سورس هماهنگ می‌کند و منطق اجرایی برنامه را تغییر نمی‌دهد.

## محدودیت محیط تست

برای اجرای کامل runtime، dependencyهای پروژه باید نصب باشند. در محیط فعلی `aiogram` نصب نبود و دسترسی شبکه برای نصب package نیز فراهم نبود؛ بنابراین runtime واقعی Telegram/FastAPI و اتصال MT5/Exchange قابل اجرای کامل نبود.

با این حال تست‌های موجود پروژه پس از اصلاح کامل پاس شدند.
