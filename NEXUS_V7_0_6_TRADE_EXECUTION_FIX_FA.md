# NEXUS V7.0.6 — Trade Execution Diagnostics & Retry Fix

## اصلاحات اصلی
- Signal Cursor دیگر قبل از اجرای موفق معامله جلو نمی‌رود.
- خطاهای موقت بروکر/قیمت/اتصال باعث Retry همان Signal در Poll بعدی می‌شوند.
- خطاهای قطعی تنظیمات سیگنال به‌صورت REJECTED ثبت و Cursor پس از آن جلو می‌رود.
- وضعیت اجرای معامله روی خود Chart نمایش داده می‌شود:
  - RECEIVED
  - ENTRY CHECK PASS
  - EXECUTED
  - LIMIT PLACED
  - REJECTED
  - OPEN FAILED - RETRYING
- Symbol واقعی بروکر روی Chart و Experts Log نمایش داده می‌شود.
- علت دقیق Reject/Open failure همراه Retcode بروکر ثبت می‌شود.
- Error text در Signal Receipt واقعاً به Backend ارسال می‌شود.
- Duplicate Position/Pending Order Protection حفظ شده است.

## نکته تست
فایل MQ5 نسخه 0.4.3 را در MetaEditor کامپایل و EX5 جدید را در assets/autotrade قرار دهید.
