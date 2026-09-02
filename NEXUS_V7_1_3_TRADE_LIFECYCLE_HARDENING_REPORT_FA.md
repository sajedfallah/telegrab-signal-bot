# NEXUS v7.1.3 — گزارش اصلاحات Trade Lifecycle

## اصلاحات
- Manual MT5 دارای انتخاب مقصد `FREE / VIP / BOTH` روی پنل چارت شد.
- مقصد انتخاب‌شده در MT5 به Backend منتقل و روی Signal ذخیره می‌شود.
- Reply Chain برای هر `(signal, channel)` به‌صورت Serial با Lock مدیریت می‌شود.
- هر Reply جدید به آخرین Reply موفق همان کانال متصل می‌شود؛ Original فقط Anchor است.
- برای Eventهای MT5 شناسه `event_id` اضافه شد و Queue/Execution Ledger بر اساس آن Idempotent شد.
- UPDATEهای متعدد یک Ticket دیگر با کلید `ticket + event_type` حذف نمی‌شوند.
- CLOSE به‌جای ایجاد پیام ریشه‌ای جدید، به انتهای Reply Chain اضافه می‌شود.
- Subjectهای استاندارد `SL CHANGED`, `TP CHANGED`, `BE ACTIVATED`, `POSITION CLOSED` اضافه شدند.
- Customer History و Daily Stats از Execution Ledger نیز تغذیه می‌شوند؛ عدم ارسال Telegram نباید باعث حذف معامله واقعی از گزارش شود.
- Failureهای Event در Ledger با وضعیت `FAILED` و متن خطا ثبت می‌شوند.
- Duplicate Event با همان `event_id` دوباره پردازش نمی‌شود.

## اعتبارسنجی
- Python compile: موفق
- Test suite موجود: `83 passed, 3 skipped`
- تست‌های جدید lifecycle: موفق
- بررسی تعادل delimiterهای فایل MQ5: موفق
- Compile واقعی MQ5 باید در MetaEditor ویندوز انجام شود؛ محیط فعلی MetaEditor ندارد.
