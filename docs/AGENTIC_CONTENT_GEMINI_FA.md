# NEXUS Agentic Content + Editorial System

این ماژول خط تولید محتوای Agentic کانال عمومی NEXUS را اجرا می‌کند و هدف آن تولید محتوای منظم، قابل‌ردیابی و کم‌حجم با هویت بصری ثابت برند است.

## Pipeline فعلی

`Topic Planner -> Curated Research -> Gemini Writer -> Creative Director -> Brand/Source Guardian -> Channel Editor -> Visual Composer -> Telegram Publisher`

برای محتوای آموزشی پایدار، Knowledge Base داخلی NEXUS مرجع اصلی است و Gemini متن را بازنویسی می‌کند. اگر Gemini موقتاً در دسترس نباشد، خروجی Curated داخلی استفاده می‌شود و Pipeline متوقف نمی‌شود.

## هویت بصری

تمام پست‌های Agentic از یک Frame ثابت NEXUS استفاده می‌کنند:

- لوگوی اصلی NEXUS
- تم Dark Navy / Charcoal
- Accentهای کنترل‌شده Cyan / Gold و رنگ مخصوص هر دسته
- عنوان، دسته محتوا، Hero Visual، تعریف یا نکات اصلی و شناسه پست
- Hero Visual موضوع‌محور توسط Creative Director تعریف می‌شود
- اگر Image AI فعال باشد، تصویر مرتبط تولید و سپس داخل Frame ثابت NEXUS Composit می‌شود
- اگر Image AI خاموش یا ناموفق باشد، Local NEXUS Visual Renderer به‌عنوان Fallback استفاده می‌شود

## دسته‌بندی و هشتگ‌ها

هر پست یک Category، Post ID و مجموعه هشتگ استاندارد دارد. نمونه‌ها:

- آموزش: `#آموزش #آموزش_ICT #ICT`
- تحلیل روزانه: `#تحلیل #تحلیل_روزانه`
- خبر: `#خبر #اخبار_بازار`
- اخبار مهم: `#اخبار_مهم #High_Impact`
- هشدار خبر: `#هشدار_خبر #Economic_Calendar`
- مدیریت ریسک: `#مدیریت_ریسک`
- مرور ستاپ: `#مرور_ستاپ`
- روانشناسی: `#روانشناسی_ترید`

در کنار این موارد، Topic Tag و Market Tag نیز در صورت امکان اضافه می‌شوند؛ مانند `#FVG`, `#Order_Block`, `#XAUUSD`, `#BTC`, `#DXY`.

شناسه هر پست پایدار و قابل جست‌وجو است. مثال:

`NX-EDU-20260904-FVG`

و Tracking Hashtag متناظر:

`#NX_EDU_20260904_FVG`

در کانال عمومی، پس از انتشار و دریافت `message_id`، لینک مستقیم Telegram نیز به Caption اضافه و در Content Registry ذخیره می‌شود.

## Editorial Gate و جلوگیری از شلوغی کانال

`ChannelEditorAgent` قبل از انتشار، Priority و سقف روزانه هر دسته را کنترل می‌کند. پیش‌فرض کلی برای محتوای غیراضطراری حداکثر 4 پست در روز است.

اخبار معمولی فقط اگر Priority کافی داشته باشند مجاز هستند. اخبار مهم و هشدارهای High Impact می‌توانند از سقف کلی عبور کنند، اما همچنان سقف اختصاصی دسته خودشان را دارند. پست خبری بدون Source URL توسط Brand/Source Guardian رد می‌شود.

## نکته مهم درباره سیستم خبر قبلی

در Source فعلی GitHub، ماژول Legacy که روی VPS از ForexFactory یا سایر منابع خبر می‌گیرد وجود ندارد. بنابراین در این نسخه، Taxonomy، Editorial Gate و Source Policy آماده است، اما مسیر Legacy News Publisher هنوز به آن متصل نشده است. برای اتصال واقعی خبرهای نسخه قدیمی باید فایل/سرویس مربوط به News Collector روی VPS یا Source اصلی آن مشخص شود و خروجی آن از همین Gate عبور داده شود.

## تنظیمات VPS

API Key نباید داخل Source، `.env.example` یا GitHub قرار بگیرد. فایل `.env` در `.gitignore` است و Key فقط روی VPS نگهداری می‌شود.

برای Windows VPS:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\configure_content_env.ps1 -DailyTime 12:00
```

این حالت به‌صورت پیش‌فرض Approval Mode را روشن نگه می‌دارد و Image AI پولی را فعال نمی‌کند.

تنظیمات اصلی:

```env
CONTENT_AGENTS_ENABLED=true
CONTENT_DAILY_TIME=12:00
CONTENT_CATCHUP_ENABLED=true
CONTENT_APPROVAL_MODE=true
CONTENT_EDITORIAL_ENABLED=true
CONTENT_MAX_POSTS_PER_DAY=4
CONTENT_AI_PROVIDER=gemini
CONTENT_AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
CONTENT_TEXT_MODEL=gemini-3.8-flash
CONTENT_IMAGE_AI_ENABLED=false
CONTENT_IMAGE_MODEL=gemini-3.1-flash-image
```

برای فعال‌سازی انتشار مستقیم پس از تست:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\configure_content_env.ps1 -DailyTime 12:00 -PublishDirectly
```

برای فعال‌سازی Image AI فقط در صورت پذیرش هزینه API:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\configure_content_env.ps1 -DailyTime 12:00 -EnablePaidImageAI
```

## Runtime

`run.py` همزمان Telegram Bot و Agentic Content Worker را اجرا می‌کند. `run_api.py` همچنان AutoTrade API را اجرا می‌کند. روی Windows Server که سرویس‌ها فعال هستند، `NEXUS-Telegram-Bot` باید به `run.py` و `NEXUS-AutoTrade-API` به `run_api.py` متصل باشد.
