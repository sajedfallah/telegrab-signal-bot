# راهنمای استقرار و مهاجرت بدون قطعی NEXUS

## اصل ایمنی

سرور فعال `46.249.98.77` تا زمان تأیید نهایی محیط Stage تغییر نمی‌کند. هیچ فایل، سرویس، دیتابیس، Firewall یا DNS روی سرور فعلی در جریان توسعه محلی دستکاری نمی‌شود.

## معماری مقصد

- یک سرویس FastAPI برای Bot webhook/polling API، وب API، WebSocket و API اکسپرت
- یک build ایستا از React تحت `/admin/`
- PostgreSQL برای Production یا SQLite/WAL فقط برای تک‌سرور کم‌بار
- Nginx به‌عنوان TLS termination و reverse proxy
- مسیر `/api/` و `/ws` به FastAPI؛ مسیر `/admin/` به build پنل
- Secretهای مجزا برای Web Admin، Bot، MT5 و Providerهای اعلان

## ترتیب مهاجرت Blue/Green

1. از دیتابیس VPS بکاپ سازگار و checksum تهیه شود؛ نسخه جاری همچنان سرویس‌دهی کند.
2. نسخه جدید روی Port/Container جداگانه با دیتابیس کپی‌شده بالا بیاید.
3. Migration فقط روی کپی اجرا و شمار رکوردها، FKها، لایسنس‌ها، پرداخت‌ها و سیگنال‌ها مقایسه شود.
4. تست Smoke شامل Login، خواندن Dashboard، WebSocket، Telegram getMe، MT5 heartbeat و یک Signal آزمایشی بدون انتشار انجام شود.
5. برای جلوگیری از دو مصرف‌کننده Telegram، فقط یک Bot polling/webhook فعال باشد.
6. در Cutover کوتاه، نسخه قدیمی Read-only/متوقف، آخرین Delta دیتابیس منتقل و Nginx به نسخه جدید سوییچ شود.
7. Health check و Audit بررسی شود؛ نسخه قدیمی و بکاپ برای Rollback حفظ شوند.

## الزامات Nginx و TLS

- فقط پورت‌های 22، 80 و 443 عمومی باشند؛ Port اپلیکیشن فقط Loopback/شبکه داخلی.
- TLS معتبر، redirect کامل HTTP به HTTPS، HSTS پس از اطمینان از دامنه و renewal خودکار.
- WebSocket با Upgrade/Connection صحیح و timeout متناسب proxy شود.
- محدودیت اندازه Body برای Receipt و Chart و Rate limit جداگانه برای Login و API اکسپرت اعمال شود.
- Headerهای `X-Content-Type-Options`, `Referrer-Policy`, CSP و Frame policy تنظیم شوند.

## Secretهای الزامی Production

- `BOT_TOKEN`
- `ADMIN_WEB_SECRET` حداقل ۳۲ کاراکتر تصادفی
- `ADMIN_WEB_USERNAME` و Password یکتا و بلند
- Token/HMAC اختصاصی API اکسپرت؛ عدم استفاده از رمز پنل در MT5
- Originهای دقیق پنل در `ADMIN_WEB_ORIGINS`
- Credentialهای Email/Push فقط در صورت فعال‌سازی واقعی Provider

## Rollback

- Nginx به Upstream قبلی برگردد.
- نسخه قدیمی Bot تنها پس از توقف کامل نسخه جدید فعال شود.
- دیتابیس جدید روی دیتابیس قدیمی overwrite نشود؛ بازگشت داده با migration معکوس بررسی‌شده یا Restore کامل انجام شود.
- تمام زمان‌های Cutover، Operator و checksum بکاپ در Audit عملیاتی ثبت شوند.
