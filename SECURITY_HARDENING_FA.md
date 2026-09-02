# NEXUS Security Hardening — v0.5.6

این بسته عمداً شامل `.env` و دیتابیس‌های Production نیست. قبل از اجرا:

1. `.env.example` را به `.env` کپی کنید.
2. `BOT_TOKEN`، `NEXUS_ADMIN_TOKEN` و `EXCHANGE_CREDENTIALS_KEY` را با مقادیر جدید و Rotate‌شده تنظیم کنید.
3. در MT5 برای Admin Mode، گزینه `InpAdminMode=true` و `InpAdminToken` را تنظیم کنید؛ Secret دیگر داخل سورس MQL5 قرار ندارد.
4. `NEXUS_ADMIN_MT5_ACCOUNTS` را فقط با حساب‌های مجاز پر کنید.
5. API را به‌صورت پیش‌فرض روی `127.0.0.1` نگه دارید؛ برای Public deployment از HTTPS، Firewall و Rate Limiting استفاده کنید.
6. قبل از Live Trading، EA را در Demo/Forward Test اجرا و رفتار Broker-specific را بررسی کنید.

## اجرای تست

```bash
python -m pytest -q
```

## اجرای Bot

```bash
python run.py
```

## اجرای AutoTrade API

```bash
python run_api.py
```

## نکته MT5

فایل `NEXUS_AutoTrade.mq5` باید در MetaEditor با Includeهای پوشه `Include/` کامپایل شود. Binary موجود در بسته باید پس از هر تغییر Source مجدداً Build و جایگزین شود.
