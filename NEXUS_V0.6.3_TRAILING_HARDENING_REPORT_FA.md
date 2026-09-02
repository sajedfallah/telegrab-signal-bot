# NEXUS v0.6.4 — Trailing Engine Hardening Report

## هدف
تمام ۷ پروفایل Trailing با همان اصل Execution Truth بازبینی شدند: هیچ وضعیت مدیریتی نباید صرفاً بر اساس درخواست داخلی EA موفق فرض شود؛ نتیجه باید از وضعیت واقعی MT5 تأیید شود.

## اصلاحات
- `ModifySL` و `ModifyTP` اکنون Retcode را بررسی و نتیجه واقعی Position را دوباره می‌خوانند.
- Partial Close برای Hedge و Netting با حجم Broker Min/Step نرمال می‌شود.
- Partial Close فقط وقتی موفق تلقی می‌شود که حجم واقعی Position بعد از معامله کاهش مورد انتظار را نشان دهد.
- Full Close فقط پس از ناپدیدشدن واقعی Position ticket موفق تلقی می‌شود.
- TP1..TP10 state فقط بعد از Execution Confirmation روی `tpN_done=1` می‌رود.
- Partial Close دارای retry با backoff نمایی محدود (1/2/4/8/16/30s) است.
- خطای Partial شامل retcode، حجم قبل، حجم درخواستی و شرح Broker می‌شود.
- Trailing 05/07 پس از Target execution تأییدشده Runner trail را اجرا می‌کنند.
- هیچ Trailing profile اجازه عقب‌بردن SL را ندارد.
- رفتار چند TP حفظ شده است: هدف نهایی حجم باقی‌مانده را می‌بندد؛ هدف‌های میانی طبق درصد snapshot شده مدیریت می‌شوند.
- هیچ screenshot برای lifecycle/trailing اضافه نشده است.

## وضعیت
Static/Unit validation در محیط ساخت قابل انجام است. Compile واقعی MQL5 و E2E با حساب MT5 باید در Windows/MetaEditor انجام شود.
