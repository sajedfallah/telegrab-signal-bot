# v0.6.0 MT5 Compile Fix

رفع خطای کامپایل در `Include/TrailingEngine.mqh`:
- helper `S(...)` که برای نوشتن Global Variables استفاده می‌شود از بخش private به public منتقل شد.
- منطق trailing و Multi-TP تغییر عملکردی دیگری در این اصلاح ندارد.
- هدف: جلوگیری از خطاهای MQL5 درباره `cannot access private member function` در خطوط مربوط به `S(...)`.

پس از جایگزینی سورس، فایل `NEXUS_AutoTrade.mq5` را در MetaEditor باز کرده و F7 را بزنید.
این پکیج از نظر Python با suite فعلی: 161 passed, 3 skipped تست شده است. کامپایل واقعی MQL5 باید داخل MetaEditor همان سیستم شما تأیید شود.
