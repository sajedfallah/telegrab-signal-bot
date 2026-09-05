# صدور سیگنال وب با تصویر واقعی MT5

## معماری نهایی

پنل وب فقط Signal مرجع و Job تصویر را ایجاد می‌کند. مرورگر هیچ نمودار مصنوعی، TradingView یا فایل جایگزینی تولید نمی‌کند. ترمینال ادمین MT5 روی VPS، با `NEXUS_ADMIN_TOKEN` و حساب موجود در `NEXUS_ADMIN_MT5_ACCOUNTS`، Job را از `OnTimer` دریافت می‌کند، نماد واقعی بروکر و تایم‌فریم سیگنال را انتخاب می‌کند، خطوط موقت Entry/SL/TP را رسم و رابط NEXUS را پنهان می‌کند. PNG واقعی همراه SHA-256 به Backend برمی‌گردد و همان renderer و routing موجود NEXUS آن را برای FREE/VIP/BOTH منتشر می‌کند.

چرخه وضعیت:

`DRAFT → WAITING_FOR_CHART → CHART_RECEIVED → FLASHCARD_READY → PUBLISHED → ACTIVE/AUTOTRADE`

در مسیر قدیمی MT5 Admin، شرط receipt معتبر Broker همچنان بدون تغییر باقی مانده است.

## API زیرساخت

- `GET /api/v1/autotrade/admin/chart-capture/jobs/next`
- `POST /api/v1/autotrade/admin/chart-capture/{job_id}/result`
- `POST /api/v1/autotrade/admin/chart-capture/{job_id}/fail`
- `GET /api/v1/admin-web/signals/{signal_id}/publication`
- `POST /api/v1/admin-web/signals/{signal_id}/chart/retry`
- `POST /api/v1/admin-web/signals/{signal_id}/publish-without-chart`
- `POST /api/v1/admin-web/signals/{signal_id}/cancel-publication`

Claim با تراکنش `BEGIN IMMEDIATE` اتمیک است. یک Signal فقط یک Job فعال دارد. کلیک تکراری وب با `request_id` و آپلود تکراری با SHA-256 idempotent است. انتشار هر مقصد نیز از claim پایدار موجود استفاده می‌کند.

## تنظیم staging

در `.env` سرور staging مقدارهای قوی و واقعی زیر را دستی تنظیم کنید (اسکریپت‌ها آن‌ها را تغییر نمی‌دهند):

```env
NEXUS_ADMIN_TOKEN=<random-secret>
NEXUS_ADMIN_MT5_ACCOUNTS=<vps-admin-account>
ADMIN_WEB_SECRET=<random-secret-at-least-32-chars>
```

در EA ادمین همان حساب:

- `InpAdminMode=true`
- `InpAdminToken` برابر Secret سرور
- URL API در Allow WebRequest ترمینال

Heartbeat تازه‌تر از ۱۲۰ ثانیه در پنل «آنلاین» نمایش داده می‌شود. Capture هر ۲ ثانیه و فقط در `OnTimer` بررسی می‌شود و مسیر مدیریت معامله در `OnTick` مسدود نمی‌شود.

## سیاست خطا

هر Claim حداکثر ۱۵ ثانیه اعتبار دارد. سه تلاش با تأخیرهای ۳ و ۷ ثانیه انجام می‌شود. بدون PNG معتبر، Signal خودکار منتشر نمی‌شود. ادمین می‌تواند Retry، Cancel یا با تأیید صریح `PUBLISH WITHOUT CHART` را اجرا کند. تصویرها فقط در `artifacts/signal_charts` و با نام ساخته‌شده از داده مرجع Backend ذخیره می‌شوند.

## چک استقرار

1. Backup دیتابیس و فایل‌های production گرفته شود؛ DB پاک نشود.
2. Backend و پنل روی staging بالا بیاید.
3. EA با MetaEditor و صفر خطا/هشدار کامپایل شود.
4. تست XAUUSD با alias واقعی بروکر، سپس FREE، VIP و BOTH اجرا شود.
5. پنهان‌شدن پنل، نمایش Entry/SL/TP، پیام واحد تلگرام و فعال‌شدن AutoTrade بعد از انتشار بررسی شود.
6. فقط پس از موفقیت staging، deploy کنترل‌شده انجام شود.

تست خودکار نمی‌تواند جای تست تصویری ترمینال متصل به feed واقعی بروکر و ارسال واقعی تلگرام را بگیرد؛ این دو مورد باید در staging اجرا و ثبت شوند.
