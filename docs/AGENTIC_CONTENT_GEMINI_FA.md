# NEXUS Agentic Content + Gemini

این ماژول تولید روزانه محتوای آموزشی ICT برای کانال عمومی NEXUS را اجرا می‌کند.

## Pipeline

`Topic Planner -> Curated Research -> Gemini Writer -> Brand Guardian -> Visual Generator -> Telegram Publisher`

در نسخه فعلی فقط محتوای آموزشی پایدار ICT به‌صورت خودکار تولید می‌شود. اخبار و تحلیل زنده بازار عمداً وارد این Worker نشده‌اند و باید در فاز جداگانه با منبع زنده و Fact Check پیاده‌سازی شوند.

## امنیت API Key

API Key نباید داخل سورس، `.env.example` یا GitHub قرار بگیرد. فایل `.env` در `.gitignore` است و کلید فقط روی VPS نگهداری می‌شود.

برای Windows VPS:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\configure_content_env.ps1 -DailyTime 12:00
```

اسکریپت Key را به‌صورت مخفی دریافت می‌کند و این تنظیمات را در `.env` قرار می‌دهد:

```env
CONTENT_AGENTS_ENABLED=true
CONTENT_DAILY_TIME=12:00
CONTENT_CATCHUP_ENABLED=true
CONTENT_APPROVAL_MODE=true
CONTENT_AI_PROVIDER=gemini
CONTENT_AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
CONTENT_TEXT_MODEL=gemini-3.8-flash
```

برای چند اجرای اول `CONTENT_APPROVAL_MODE=true` بماند تا پست فقط برای ادمین‌ها Preview شود. پس از تأیید کیفیت، می‌توان مقدار آن را `false` کرد تا انتشار مستقیم در `PUBLIC_CHANNEL_ID` انجام شود.

## Runtime

`run.py` همزمان Telegram Bot و Agentic Content Worker را اجرا می‌کند. AutoTrade API همچنان با `run_api.py` اجرا می‌شود. بنابراین `start_all_windows.bat` بدون تغییر، API و Runtime جدید را بالا می‌آورد.

اگر Gemini موقتاً در دسترس نباشد، Writer به Knowledge Base داخلی NEXUS برمی‌گردد و کل Pipeline به دلیل خطای AI متوقف نمی‌شود.
