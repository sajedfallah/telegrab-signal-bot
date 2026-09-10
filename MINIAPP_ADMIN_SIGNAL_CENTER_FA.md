# پنل ادمین Signal Center در Telegram Mini App

این قابلیت یک Control Plane جدید برای ادمین است و مسیر فعلی MT5 Admin را حذف نمی‌کند.

## معماری

`Mini App Admin → Backend → NEXUS ChartAgent → Screenshot → Signal Card → Telegram → Client EA`

- Mini App فقط Symbol، Direction، Entry، SL و Destination را دریافت می‌کند.
- Backend چهار TP را با ضرایب `1R / 1.5R / 2R / 3R` یک‌بار محاسبه و در `signal_targets` ذخیره می‌کند.
- Signal با issuer سازگار `WEB_ADMIN` وارد همان lifecycle موجود می‌شود.
- NEXUS ChartAgent همان `signal_chart_capture_jobs` را poll می‌کند و screenshot را می‌سازد.
- Telegram فقط بعد از دریافت screenshot معتبر منتشر می‌شود.
- Client EAها همان targets ذخیره‌شده را دریافت می‌کنند.

## Stateها

- `DRAFT`
- `READY`
- `WAITING_FOR_MT5`
- `PROCESSING`
- `SCREENSHOT_READY`
- `PUBLISHED`
- `FAILED`

وضعیت orchestration در جدول `miniapp_admin_signal_requests` نگهداری می‌شود. داده canonical معامله همچنان در `signals` و `signal_targets` است.

## امنیت و Idempotency

- امضای Telegram `initData` در backend بررسی می‌شود.
- شناسه Telegram باید در `ADMIN_IDS` باشد.
- `request_id` یکتا است و retry شبکه Signal دوم ایجاد نمی‌کند.
- دستورهای مدیریت پوزیشن فقط برای Signal متعلق به همان MT5 Admin account پذیرفته می‌شوند.

## تنظیمات

```env
MINIAPP_ADMIN_URL=https://YOUR_DOMAIN/miniapp/admin.html
MINIAPP_SYMBOL_DIGITS_JSON={"XAUUSD":2,"USDJPY":3,"EURUSD":5}
```

`MINIAPP_ADMIN_URL` باید HTTPS باشد. بعد از تنظیم، دکمه پنل Mini App در منوی ادمین تلگرام ظاهر می‌شود.

## استقرار Windows Server

```powershell
Set-Location 'C:\NEXUS_V065_FINAL_TEST'
git fetch origin
git switch codex/integrate-miniapp-admin-v065
git pull --ff-only origin codex/integrate-miniapp-admin-v065
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest tests\test_miniapp_admin_signal_center.py -q
```

سپس مقادیر بالا را در `.env` تنظیم و سرویس API/Bot را با روش فعلی سرور restart کنید.

## MQL5

هیچ فایل MQL5 تغییر نکرده است. Backend هر دو route زیر را می‌پذیرد:

- `/api/v1/autotrade/admin/chart-capture/next`
- `/api/v1/autotrade/admin/chart-capture/jobs/next`

همچنین payload قدیمی `image_base64` و payload جدید `chart_base64` هر دو پشتیبانی می‌شوند. بنابراین `mt5/NEXUS_ChartAgent/NEXUS_ChartAgent.mq5` فعلی Production بدون تغییر کار می‌کند و Compile جدید EX5 لازم نیست.

## Rollback

قبل از استقرار SHA فعلی Production را ثبت کنید. برای rollback، سرویس‌ها را متوقف کنید، همان SHA قبلی را checkout کنید و سرویس‌ها را دوباره راه‌اندازی کنید. دیتابیس را reset یا حذف نکنید؛ migrationها افزایشی هستند و جدول‌های جدید در نسخه قدیمی نادیده گرفته می‌شوند.
