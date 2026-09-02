# NEXUS v7.1.0 — Production Hardening & Pricing

## Pricing

قیمت رسمی سرویس‌ها فقط USDT است:

### VIP SIGNAL
- 1 Month: 25 USDT
- 3 Months: 69 USDT
- 6 Months: 129 USDT
- 1 Year: 229 USDT

### AUTO TRADE VIP
- 1 Month: 40 USDT
- 3 Months: 110 USDT
- 6 Months: 200 USDT
- 1 Year: 360 USDT

### Setup & Activation
- 1 Month: 15 USDT
- 3 Months: 15 USDT
- 6 Months: 7.5 USDT
- 1 Year: 0 USDT

پرداخت ریالی فقط یک روش پرداخت است. مبلغ ریالی از قیمت USDT و نرخ لحظه‌ای USDT/RIAL در زمان ایجاد فاکتور محاسبه می‌شود. فاکتور ریالی به‌صورت پیش‌فرض 15 دقیقه اعتبار دارد و پس از انقضا باید نرخ جدید دریافت شود.

## Security / Reliability Fixes

- لغو/تعلیق/Revoked شدن License اکنون دسترسی Auto Trade را فوراً قطع می‌کند.
- Signal تا زمان انتشار موفق در کانال‌ها برای Auto Trade قابل دریافت نیست.
- Receipt کاربر هرگز وضعیت global یک Signal را تغییر نمی‌دهد.
- TXID به‌صورت case-insensitive یکتا است.
- Notification queue دارای atomic claim است.
- FastAPI از lifespan استفاده می‌کند.
- رفتار پایان اشتراک Auto Trade قابل تنظیم است: A / B / C.
- Account Number و Broker Server برای MT5 کنترل می‌شوند.

## Data Model

مدل‌های canonical جدید:

- `plans`
- `subscriptions`
- `licenses`
- `invoices`
- `payments`

مدل‌های legacy برای backward compatibility حفظ شده‌اند.

## MT5

- EA source به v0.5.0 ارتقا یافت.
- TP1 تا TP10 در API/source پشتیبانی می‌شود.
- Policy C برای پایان اشتراک: بستن Positionها و حذف Pending Orderهای NEXUS.

> EX5 باید از سورس v0.5.0 در MetaEditor کامپایل مجدد شود.
