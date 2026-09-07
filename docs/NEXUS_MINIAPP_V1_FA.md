# NEXUS Mini App V1 — Approved V4 Implementation

این نسخه، طراحی تأییدشده V4 را به یک Mini App واقعی و قابل اجرا تبدیل می‌کند.

## ساختار

- `miniapp/index.html` — پوسته Telegram Web App
- `miniapp/styles.css` — رابط Dark/Premium ریسپانسیو
- `miniapp/app.js` — ناوبری Home / Signals / Subscriptions / Products / My Account
- `app/miniapp_runtime.py` — Bootstrap API + اعتبارسنجی Telegram initData + Static hosting
- `run_api.py` — نصب Mini App روی FastAPI موجود

## قواعد V4 حفظ‌شده

- Home برای همه کاربران ساده و تمیز است.
- Home وضعیت EA/MT5/License یا Today Status نشان نمی‌دهد.
- Products در Home لیست نمی‌شود و صفحه مستقل دارد.
- Public NEXUS Channel در Home قرار دارد.
- Signals فقط Free Signal و VIP Signal دارد.
- Subscriptions و My Account صفحات مستقل دارند.

## مسیرهای اجرا

- UI: `/miniapp/`
- Bootstrap API: `/api/miniapp/bootstrap`
- Health: `/api/miniapp/health`

## امنیت Telegram

اگر Mini App داخل Telegram باز شود، `Telegram.WebApp.initData` به Backend ارسال می‌شود و با `BOT_TOKEN` و HMAC-SHA256 اعتبارسنجی می‌شود. initData نامعتبر HTTP 401 دریافت می‌کند. اجرای مستقیم در مرورگر به عنوان Preview Mode مجاز است و اطلاعات خصوصی حساب را برنمی‌گرداند.

## Deploy روی VPS

پس از قرار گرفتن Feature روی VPS:

```powershell
cd C:\NEXUS_V065_FINAL_TEST
.\.venv\Scripts\python.exe -m pytest -q tests/test_miniapp_runtime.py
Restart-Service NEXUS-AutoTrade-API
```

سپس از داخل خود VPS:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/api/miniapp/health
```

باید `ok = true` برگردد.

برای استفاده واقعی در Telegram باید API از طریق یک دامنه HTTPS عمومی Reverse Proxy شود؛ مثال نهایی باید چیزی شبیه زیر باشد:

`https://app.your-domain.com/miniapp/`

سپس همان HTTPS URL در BotFather به عنوان Web App URL / Menu Button تنظیم می‌شود.

## وضعیت V1

این مرحله UI، Telegram bridge، session validation، routes و bootstrap را آماده می‌کند. اتصال مستقیم عملیات خرید، وضعیت واقعی Subscription و AutoTrade account data به DB در مرحله بعد انجام می‌شود؛ در V1 دکمه‌های عملیاتی از `Telegram.WebApp.sendData` به Bot تحویل داده می‌شوند تا منطق فعلی Bot حفظ شود.
