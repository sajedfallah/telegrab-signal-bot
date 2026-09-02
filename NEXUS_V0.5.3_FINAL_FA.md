# NEXUS v0.5.3 FINAL — Two-Way Chart Sync

اصلاحات این نسخه:
- Screenshot از چارت باز واقعی کاربر؛ بدون ChartOpen/default chart.
- Signal/Result/Reply بدون protect_content تا اعداد قابل Copy باشند.
- MT5 OPEN / UPDATE / CLOSE در Backend پشتیبانی می‌شود.
- تغییر SL/TP از MT5 به‌صورت متن روی Reply همان سیگنال ارسال می‌شود؛ Screenshot فقط OPEN/CLOSE است.
- License EditBox قابل ویرایش و selected می‌شود.

## اجرا
1. فایل MQ5 را در MetaEditor باز کنید و Compile کنید.
2. Backend را از پروژه فعلی اجرا کنید.
3. تست‌ها: `python -m pytest -q`
4. EA را روی ePlanet-MT5 Demo نصب و تست کنید.

این بسته شامل `.env` و `.ex5` نیست؛ تنظیمات محرمانه و فایل کامپایل‌شده نسخه قبلی عمداً منتقل نشده‌اند.
