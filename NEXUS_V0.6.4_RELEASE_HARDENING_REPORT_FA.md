# NEXUS v0.6.4 — Release Hardening Report

## هدف
بستن سه شکاف باقیمانده در v0.6.3: هویت Admin در Fresh DB، جلوگیری از Duplicate Execution در Live-State Repair، و Retry پایدار انتشار Telegram پس از Receipt معتبر.

## اصلاحات
1. **Fresh DB Admin Receipt (P0):** هنگام Admin authorization هویت سیستمی Admin به‌صورت idempotent در `users` provision می‌شود؛ `mark_signal_receipt` نیز defense-in-depth دارد. بنابراین Receipt معتبر MT5 به دلیل Foreign Key نباید به HTTP 500 تبدیل شود.
2. **Execution Ledger Identity:** Live-State Repair ابتدا با `telegram_id + ticket + signal_id + event_type` رکورد اجرای موجود را پیدا و همان را reconcile می‌کند؛ `event_id` صرفاً شناسه انتقال است و باعث Duplicate Business Execution نمی‌شود.
3. **Telegram Publication Retry:** سیگنال‌های MT5_ADMIN با Receipt معتبر `EXECUTED/PENDING/ACTIVATED` که یکی از channelهای موردنیاز را ندارند، در `list_mt5_publication_retries` قابل بازیابی‌اند و Worker هر 5 ثانیه انتشار ناقص را Retry می‌کند.
4. **Publication Gate حفظ شد:** `REJECTED/FAILED/FAILED_RETRYABLE` هرگز وارد Publication Queue نمی‌شوند.
5. **MT5 Live Center حفظ شد:** پنل Admin فقط از Live Snapshot فعلی MT5 تغذیه می‌شود و stale signal history را به‌عنوان وضعیت زنده نمایش نمی‌دهد.

## Verification
- `python -m py_compile app/db.py app/autotrade/api.py app/autotrade/service.py app/main.py` — PASS
- `python -m pytest -q` — **209 passed, 3 skipped**
- تست Fresh DB Admin Receipt — PASS
- تست جلوگیری از Duplicate Business Execution — PASS
- تست Durable Telegram Publication Retry — PASS

## محدودیت
MetaEditor/MT5 واقعی و Telegram production در محیط build در دسترس نبود؛ بنابراین این گزارش **Production Ready** اعلام نمی‌کند. E2E واقعی باید روی همان MT5 Demo/Broker انجام شود.
