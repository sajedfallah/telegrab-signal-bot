# گزارش ادغام NEXUS Auto Trade با NEXUS CORE v7.0.1

نسخه مبنا: NEXUS CORE v7.0.1 — REPORT CARD FINAL  
ماژول اضافه‌شده: NEXUS Auto Trade MT5 v0.3.0 Setup Wizard

## موارد حفظ‌شده از v7.0.1
- Report Card جدید و منطق گزارش روزانه/هفتگی
- `build_report_card` و آمار مستقل Forex/Crypto برای FREE/VIP
- تنظیم `REPORT_FA_FONT_PATH`
- همه Routerها، سرویس‌ها، تست‌ها و منطق فعلی ربات

## موارد Auto Trade اضافه‌شده
- FastAPI Auto Trade API و `run_api.py`
- تولید و مدیریت License Key با فرمت `NXS-YYYY-XXXX-XXXX`
- Binding هر لایسنس به یک حساب MT5
- Heartbeat و session tracking
- دریافت سیگنال‌های فعال Forex از جدول اصلی `signals`
- Signal receipt / command receipt و ACK
- Command bridge برای Break Even, Partial Close, Trailing, Update SL/TP و Close
- Snapshot تنظیمات Trailing و Entry Deviation
- هفت پروفایل Trailing NEXUS_TRAIL_01 تا NEXUS_TRAIL_07
- سورس MT5 با Setup Wizard روی چارت
- API URL داخلی EA: `http://127.0.0.1:8080`

## تست
- Python compileall: PASS
- Pytest: 28 passed

## اجرای محلی
1. `setup_windows.bat` برای نصب وابستگی‌ها
2. `python run_api.py` برای API روی پورت 8080
3. `start_windows.bat` یا `python run.py` برای ربات
4. در MT5 آدرس `http://127.0.0.1:8080` را در Allow WebRequest اضافه کنید.
5. فایل `mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5` را در MetaEditor Compile کنید.

برای Production باید URL داخلی EA از localhost به دامنه HTTPS واقعی NEXUS تغییر داده شود.
