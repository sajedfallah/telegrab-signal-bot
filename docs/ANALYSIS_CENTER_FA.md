# NEXUS Analysis Center — راهنمای اجرا

این ماژول برای تحلیل و انتشار خودکار چارت توسط ادمین ساخته شده است.

## قابلیت‌ها

- تحلیل همزمان چند نماد با Session مستقل برای هر نماد.
- تحلیل پایه با دو تصویر `1H` و `15M`.
- `1H` برای Context/Bias و `15M` برای DP/FVG/OB/Liquidity.
- ورود فقط بر اساس تریگر `5M`؛ لمس ناحیه به‌تنهایی سیگنال نیست.
- بررسی نواحی رسم‌شده و اصلاح ناحیه اشتباه توسط مدل Vision.
- لحن ثابت، روان و فارسی برای تمام تحلیل‌ها و آپدیت‌ها.
- هر آپدیت فقط Context همان نماد و همان Session را می‌بیند.
- آپدیت چارت به پیام اصلی همان تحلیل در گروه Telegram ریپلای می‌شود.
- Session تا زمانی که ادمین «پایان تحلیل» را نزند ACTIVE باقی می‌ماند.
- یک نماد در هر لحظه فقط یک Session فعال دارد؛ نمادهای مختلف می‌توانند همزمان ACTIVE باشند.

## متغیرهای محیطی

حداقل این مقدار را در `.env` تنظیم کنید:

```env
ANALYSIS_CENTER_ENABLED=true
ANALYSIS_TARGET_CHAT_ID=-1001234567890
```

`ANALYSIS_TARGET_CHAT_ID` باید ID گروه/سوپرگروهی باشد که تحلیل‌ها در آن منتشر می‌شوند.

اگر گروه Forum است و تحلیل‌ها باید در یک Topic خاص قرار بگیرند:

```env
ANALYSIS_TARGET_THREAD_ID=123
```

### مدل Vision

به‌صورت پیش‌فرض Analysis Center از تنظیمات AI موجود در Content Agent استفاده می‌کند. در صورت نیاز می‌توانید آن را مستقل تنظیم کنید:

```env
ANALYSIS_AI_API_KEY=YOUR_KEY
ANALYSIS_AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
ANALYSIS_AI_MODEL=YOUR_VISION_CAPABLE_MODEL
ANALYSIS_AI_TIMEOUT=60
```

مدلی که در `ANALYSIS_AI_MODEL` انتخاب می‌شود باید ورودی تصویر (`image_url` در Chat Completions سازگار با OpenAI) را پشتیبانی کند.

تنظیمات اختیاری:

```env
ANALYSIS_MAX_CAPTION_CHARS=950
ANALYSIS_HISTORY_LIMIT=6
```

## جریان کار ادمین

1. از پنل مدیریت وارد `🧠 مرکز تحلیل` شوید.
2. `➕ تحلیل جدید` را انتخاب کنید.
3. نماد را انتخاب کنید.
4. تصویر `1H` را ارسال کنید.
5. تصویر `15M` را ارسال کنید.
6. ربات تحلیل مولتی‌تایم‌فریم را تولید و در گروه منتشر می‌کند.
7. برای آپدیت، `🔄 آپدیت تحلیل` را انتخاب کنید، نماد فعال را بزنید و فقط عکس جدید را ارسال کنید.
8. ربات متن جدید را با Context همان Session تولید و به پیام اصلی همان تحلیل Reply می‌کند.
9. در پایان سناریو، `✅ پایان تحلیل` را بزنید و نماد را انتخاب کنید.

## مثال همزمانی

می‌توان این Sessionها را همزمان فعال داشت:

- XAUUSD — ACTIVE
- BTCUSD — ACTIVE
- SOLUSD — ACTIVE

آپدیت BTCUSD هیچ Context یا Update از XAUUSD/SOLUSD دریافت نمی‌کند.

## دیتابیس

ماژول هنگام Startup دو جدول را به‌صورت خودکار می‌سازد:

- `analysis_sessions`
- `analysis_updates`

برای هر Session، `root_chat_id` و `root_message_id` ذخیره می‌شود تا تمام Updateها به Root Analysis درست Reply شوند.

## نکته عملیاتی

ربات باید در گروه مقصد مجوز ارسال Photo و Message داشته باشد. برای گروه‌های Forum نیز باید اجازه ارسال در Topic مقصد را داشته باشد.
