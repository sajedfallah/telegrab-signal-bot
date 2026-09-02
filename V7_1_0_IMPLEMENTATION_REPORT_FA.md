# NEXUS v7.1.0 — گزارش اجرای اصلاحات

این Build بر اساس نسخه آپلودشده v7.0.9 و مشکلات شناسایی‌شده در بررسی GitHub/سورس اصلاح شده است.

## اصلاحات بحرانی

- لغو/تعلیق/Revoked شدن License باعث Hard Revoke دسترسی Auto Trade می‌شود.
- Signal فقط پس از Publication موفق و در وضعیت `ACTIVE` در Auto Trade قابل دریافت است.
- Receipt مربوط به Signal دیگر Lifecycle سراسری Signal را تغییر نمی‌دهد.
- TXID به‌صورت case-insensitive یکتا شده و قبل از ثبت دوباره بررسی می‌شود.
- Payment reservation در صورت شکست Promo/Campaign rollback می‌شود.
- Notification queue دارای `claimed_at` و atomic claim/release است.
- FastAPI از `lifespan` استفاده می‌کند و API version به `0.3.0` ارتقا یافته است.

## سیستم فروش

### VIP SIGNAL

- 1 Month — 25 USDT
- 3 Months — 69 USDT
- 6 Months — 129 USDT
- 1 Year — 229 USDT

### AUTO TRADE VIP

- 1 Month — 40 USDT
- 3 Months — 110 USDT
- 6 Months — 200 USDT
- 1 Year — 360 USDT

### Setup & Activation

- 1 Month — 15 USDT
- 3 Months — 15 USDT
- 6 Months — 7.5 USDT
- 1 Year — 0 USDT

Setup برای Renewal تکرار نمی‌شود؛ فقط Initial Activation و Upgrade از VIP به Auto Trade شامل آن است.

## پرداخت ریالی

- قیمت مرجع سرویس فقط USDT است.
- نرخ USDT/RIAL از Provider قابل تنظیم دریافت می‌شود.
- Manual Override از پنل Admin اضافه شد.
- URL Provider از پنل Admin قابل تغییر است.
- TTL پیش‌فرض فاکتور ریالی 15 دقیقه است و قابل تغییر است.
- مبلغ ریالی با Decimal و `ROUND_CEILING` به سمت بالا گرد می‌شود.
- نرخ، مبلغ USDT و مبلغ نهایی در Invoice snapshot ذخیره می‌شوند.

## Upgrade / Extend

- تمدید از پایان اشتراک فعال محاسبه می‌شود.
- Upgrade از VIP به Auto Trade اعتبار روزهای باقی‌مانده را محاسبه می‌کند.
- Proration از Admin قابل فعال/غیرفعال شدن است.
- Setup Fee برای Renewal صفر است.

## Data Model

Canonical tables: `plans`, `subscriptions`, `licenses`, `invoices`, `payments`.
مدل‌های قدیمی برای سازگاری حفظ شده‌اند و Catalog جدید یک‌بار به v7.1 migrate می‌شود.

## MT5

- Source به v0.5.0 ارتقا یافت.
- Expiry policyهای A/B/C اضافه شد.
- Policy C شامل بستن Positionهای NEXUS و حذف Pending Orderهای NEXUS است.
- Broker Server binding بررسی می‌شود.
- TP1 تا TP10 در payload و EA پشتیبانی می‌شود.

## Validation

- Pytest: **63 passed**
- Python compileall: **passed**
- Static source checks: **passed**
- EX5 عمداً حذف شده است چون Binary قبلی متعلق به v0.4.5 بود؛ باید سورس v0.5.0 در MetaEditor کامپایل شود.

## حجم تغییرات نسبت به فایل‌های اصلی آپلودشده

- `app/db.py`: +335 / -43
- `app/main.py`: +204 / -124
- `app/config.py`: +16 / -12
- `app/ui.py`: +7 / -6
- `app/autotrade/service.py`: +20 / -6
- `app/autotrade/api.py`: +26 / -9

## Runtime artifacts حذف‌شده

`nexus_bot.db`, `nexus_fsm.db`, logs، backups، caches، `__pycache__` و EX5 قدیمی از بسته نهایی حذف شدند.
