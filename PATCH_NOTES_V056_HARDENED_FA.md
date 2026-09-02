# NEXUS v0.5.6 — Hardening Patch Notes

این نسخه با حفظ ساختار اصلی پروژه اصلاح شده است.

## اصلاحات اصلی

- رفع ناسازگاری Authorization در Standard Mode برای polling سیگنال و command.
- اضافه شدن Validation هندسه معامله در Signal Creation و Trade Event.
- جلوگیری از مقادیر non-finite و محدوده‌های غیرمنطقی در Trade Event.
- اعتبارسنجی واقعی PNG/JPEG با Pillow و محدودیت ابعاد/حجم.
- اصلاح Idempotency برای Trade Eventهای Legacy با event_id خالی؛ fallback اکنون deterministic است.
- انتقال گزارش‌دهی شبکه‌ای تغییرات Position از `OnTick` به `OnTimer`.
- انتقال Manual OPEN event به queue محلی timer-driven در EA تا WebRequest/Screenshot داخل `OnTradeTransaction` اجرا نشود.
- حذف Secretهای Admin از سورس MQL5؛ Admin اکنون فقط با Input و allow-list سمت Backend فعال می‌شود.
- حذف duplicate cursor load در EA.
- اصلاح `run_api.py` تا متغیرهای Host/Port از `.env` قبل از خواندن محیط بارگذاری شوند.
- اضافه شدن `.gitignore` برای Secret، Database، Cache و Runtime artifacts.
- حذف `.env`، دیتابیس‌های Runtime و Cacheها از بسته توزیعی.
- اضافه شدن تست‌های P0 جدید.

## تست نهایی

```text
100 passed, 3 skipped
Python compileall: PASS
MQL5 source brace/parenthesis balance: PASS
Archive integrity: PASS
Production .env / DB / pyc artifacts in distribution ZIP: NONE
```

## نکته MT5

به دلیل نبود MetaEditor/MT5 compiler در محیط اصلاح، فایل `.mq5` به‌صورت Static بررسی و اصلاح شده اما `NEXUS_AutoTrade.ex5` نمی‌تواند در این محیط مجدداً Compile شود. قبل از Live Trading، Source باید در MetaEditor با Includeهای موجود Compile شود و EX5 حاصل جایگزین Binary قبلی گردد.
