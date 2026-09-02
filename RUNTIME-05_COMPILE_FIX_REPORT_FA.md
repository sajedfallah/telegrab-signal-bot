# گزارش اصلاح Compile Runtime-05

## خطاهای گزارش‌شده در MetaEditor
- `undeclared identifier 'shot'` در خط 1470: در رویداد PENDING اسکرین‌شات نباید ارسال شود. متغیر تعریف‌نشده با رشته خالی `""` جایگزین شد.
- هشدار `variable 'tabs' not used` در خط 804: آرایه تب‌های legacy اکنون برای عناوین زیرتب‌های Settings استفاده می‌شود، بنابراین warning حذف می‌شود و سازگاری تست‌ها حفظ می‌شود.

## سیاست Lifecycle
اسکرین‌شات فقط در زمان صدور Signal اصلی گرفته می‌شود. رویدادهای بعدی شامل OPEN/CLOSE/UPDATE/PENDING فقط بدون chart_base64 ارسال می‌شوند.

## تست
`185 passed, 3 skipped`

> کامپایل نهایی باید داخل MetaEditor/MT5 روی ویندوز انجام شود؛ محیط فعلی Linux به MetaEditor compiler دسترسی ندارد.
