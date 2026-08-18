# NEXUS CORE v7.0 — نسخه مبنا

این ریپازیتوری نسخه `NEXUS CORE v7.0.0` را به‌عنوان **اولین نسخه مناسب اجرای واقعی و مبنای توسعه آینده** نگهداری می‌کند.

NEXUS یک ربات ساده ارسال سیگنال نیست؛ هسته کسب‌وکار تلگرامی برای مدیریت کاربر، اشتراک، لایسنس، پرداخت، رفرال، سیگنال، گزارش و تحلیل عملکرد است.

## امکانات فعلی

- ورود فارسی/English و امکان تغییر زبان
- کنترل عضویت کانال عمومی
- منوی کاربر بر اساس دسترسی واقعی
- خرید اشتراک با ریال/USDT
- تأیید/رد پرداخت توسط ادمین
- لایسنس VIP و Auto-Trade entitlement
- تمدید و Upgrade بدون از دست رفتن زمان باقی‌مانده
- Referral و NEXUS Points
- تخفیف، کمپین، Broadcast، CRM، Audit و Backup
- Signal Center کامل
- TP داینامیک با تعداد دلخواه
- Lot برای Forex و Leverage برای Crypto
- ۷ مدل ثابت NEXUS Trailing
- انتشار FREE/VIP/BOTH
- Break Even، Partial، Trailing، Update TP/SL
- Close/Result با یک عکس چارت قاب‌شده + کپشن
- گزارش روزانه/هفتگی ادمین
- گزارش روزانه/هفتگی کانال با تفکیک FREE و VIP
- داشبورد Analytics بر اساس بازه، نماد، Trailing و کانال
- FSM پایدار SQLite که با Restart معمولی از بین نمی‌رود

## شروع سریع

```cmd
py -3.11 -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt --timeout 120 --retries 10
python run.py
```

یا:

```cmd
setup_windows.bat
start_windows.bat
```

فایل `.env.example` را به `.env` کپی کن و اطلاعات واقعی را فقط روی سیستم اجرا وارد کن. فایل `.env` نباید داخل Git قرار گیرد.

## تست

```cmd
run_tests.bat
```

نسخه مبنای v7.0 دارای ۲۱ تست Pass شده است.

## مستندات کامل

- `README.md` — معرفی کامل ریپازیتوری و نقشه فایل‌ها
- `docs/PROJECT_OVERVIEW.md` — تعریف محصول و قواعد اصلی
- `docs/FUNCTIONAL_SPEC.md` — رفتار دقیق کاربر/ادمین/پرداخت/سیگنال
- `docs/ARCHITECTURE.md` — معماری نرم‌افزار
- `docs/PROJECT_HISTORY.md` — تاریخچه مسیر پروژه تا v7
- `docs/OPERATIONS.md` — نصب، اجرا و عملیات
- `docs/ROADMAP.md` — مسیر توسعه v7.1 تا v10
- `docs/AI_HANDOFF.md` — اطلاعات لازم برای تحویل پروژه به AI/توسعه‌دهنده دیگر
- `AGENTS.md` — قواعد کار Agentهای کدنویسی
- `SECURITY.md` — قواعد امنیت و فایل‌های حساس

## مراحل آینده

اولویت بعدی `v7.1 Production & Monitoring` است. بعد از پایدارسازی Production، مسیر پیشنهادی به‌ترتیب Mini App، Vision AI و در نهایت Auto Trade واقعی است.
