# NEXUS v0.5.7 — MT5 History Reconciliation

این نسخه یک لایه Reconciliation برای MT5 اضافه می‌کند.

## رفتار
- EA هر 5 دقیقه History معاملات NEXUS را در بازه پیش‌فرض 72 ساعت بررسی می‌کند.
- معاملات با Magic Number خود NEXUS گروه‌بندی می‌شوند.
- OPEN و CLOSE به‌صورت idempotent به Backend ارسال می‌شوند.
- Backend رویدادهای تکراری را دوباره ثبت نمی‌کند.
- اگر CLOSE از Event زنده جا افتاده باشد، Signal در DB با زمان واقعی رویداد و P/L خالص MT5 بسته می‌شود.
- P/L بسته‌شدن شامل PROFIT + SWAP + COMMISSION است.
- Reconciliation هیچ پیام Telegram جدیدی منتشر نمی‌کند.
- معاملات نامرتبط که Signal ID در Comment ندارند، به Signal تبدیل نمی‌شوند.

## نتیجه گزارش‌ها
Signal Statistics و Daily/Weekly Signal Reports همچنان از جدول `signals` استفاده می‌کنند، اما حالا در صورت از دست رفتن Event، Reconciliation می‌تواند همان `signals` را از روی History واقعی MT5 اصلاح کند.

AutoTrade Daily Report از execution ledger استفاده می‌کند و با زمان رویداد تاریخی ثبت می‌شود، نه زمان اجرای Reconciliation.

## نصب
1. فایل `mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5` را با MetaEditor کامپایل کنید.
2. EX5 تولیدشده را روی MT5 جایگزین کنید.
3. API URL را در WebRequest Allow List نگه دارید.
4. EA را با نسخه 0.5.7 اجرا کنید.

> این محیط MetaEditor/MT5 را در اختیار ندارد؛ بنابراین EX5 جدید از اینجا کامپایل نشده است. Source MQ5 آماده کامپایل است.
