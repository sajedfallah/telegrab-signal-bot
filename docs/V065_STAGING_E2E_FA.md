# NEXUS v0.6.5 — Staging E2E Gate

این runbook فقط برای staging است. به سرویس‌های Production با نام‌های `NEXUS-Telegram-Bot` و `NEXUS-AutoTrade-API` دست نمی‌زند و هیچ کانال واقعی تلگرام را مقصد تست نمی‌کند.

## پیش‌نیازهای قطعی

- checkout در `C:\NEXUS_V065_STAGING` روی SHA موردنظر integration باشد.
- `NEXUS_ENV=staging` و API روی `http://127.0.0.1:18080` اجرا شود.
- `FREE_CHANNEL_*` و `VIP_CHANNEL_*` فقط مقصد sandbox باشند؛ اگر این شرط اثبات نشده، مرحلهٔ publish اجرا نمی‌شود.
- ChartAgent مستقل باشد، `InpApiBaseUrl=http://127.0.0.1:18080` و `InpPollSeconds=2` داشته باشد.
- `NEXUS_Screenshot.tpl` با `scripts/provision_screenshot_template.py` پاک‌سازی و در MT5 نصب شده باشد.

## مرحلهٔ ۱: preflight بدون تغییر state

روی VPS و از checkout staging اجرا کنید:

```powershell
python scripts\staging_preflight.py --base-url http://127.0.0.1:18080
```

خروجی قابل‌قبول باید `"ok": true`، `"missing_required_paths": []` و note مربوط به read-only را نشان دهد. این مرحله هیچ Signal، job، دعوت VIP یا پیام تلگرام تولید نمی‌کند.

## مرحلهٔ ۲: E2E کنترل‌شده (پس از تأیید مقصد sandbox)

پس از ثبت screenshot از خروجی مرحلهٔ ۱ و تأیید انسانیِ sandbox بودن هر دو channel:

1. از Web Admin یک signal staging با یک `request_id` جدید بسازید.
2. فقط یک ChartAgent مجاز آن را claim کند.
3. وضعیت‌ها باید به‌ترتیب `WAITING_FOR_CHART → CHART_RECEIVED → PUBLISHED` باشند.
4. تصویر و flashcard را بررسی کنید: Entry، SL، همهٔ TPها و tagهای مرکز‌شده روی level خود باشند.
5. یک receipt AutoTrade sandbox را ثبت و audit/event ledger را بررسی کنید.

اگر هر مرحله fail شد، job را با همان `request_id` دوباره ایجاد نکنید؛ status و `error_text` همان job را ذخیره و root cause را در issue ثبت کنید. rollback فقط با بازگردانی SHA قبلی staging و backup DB انجام می‌شود؛ DB wipe ممنوع است.
