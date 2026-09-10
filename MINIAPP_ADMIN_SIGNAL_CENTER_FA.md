# پنل ادمین Signal Center در Telegram Mini App

این قابلیت یک Control Plane جدید برای ادمین است و مسیر فعلی MT5 Admin را حذف نمی‌کند.

## معماری

`Mini App Admin → Backend → MT5 Admin EA → Screenshot → Signal Card → Telegram → Client EA`

- Mini App فقط Symbol، Direction، Entry، SL و Destination را دریافت می‌کند.
- Backend چهار TP را با ضرایب `1R / 1.5R / 2R / 3R` یک‌بار محاسبه و در `signal_targets` ذخیره می‌کند.
- Signal با issuer سازگار `WEB_ADMIN` وارد همان lifecycle موجود می‌شود.
- MT5 Admin EA همان `signal_chart_capture_jobs` موجود را poll می‌کند و screenshot را می‌سازد.
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
Set-Location 'C:\path\to\NEXUS'
git fetch origin
git pull --ff-only
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m pytest tests\test_miniapp_admin_signal_center.py -q
```

سپس مقادیر بالا را در `.env` تنظیم و سرویس API/Bot را با روش فعلی سرور restart کنید.

## MQL5

در این تغییر فایل MQL5 اصلاح نشده است؛ شاخه کاری از قبل دارای polling و upload کامل chart-capture job است. اگر EX5 مستقر روی VPS قبل از قابلیت Web MT5 chart capture ساخته شده باشد، باید `mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5` همان شاخه دوباره compile و EX5 جایگزین شود.
