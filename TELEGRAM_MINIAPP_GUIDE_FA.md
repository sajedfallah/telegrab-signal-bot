# راهنمای مینی‌اپ تلگرام NEXUS

این مینی‌اپ یک رابط موبایل فارسی برای قابلیت‌های کاربر و ادمین NEXUS است و از همان پایگاه دادهٔ ربات، API اتوترید و پنل وب استفاده می‌کند.

## قابلیت‌ها

- احراز هویت واقعی Telegram `initData` با HMAC و محدودیت زمانی
- داشبورد کاربر، سطح، اشتراک، رفرال و وضعیت حساب MT5
- مشاهدهٔ سیگنال‌های مجاز بر اساس دسترسی FREE/VIP
- وضعیت معاملات، آمار روز، تاریخچه و درخواست تغییر حساب
- مدیریت ریسک به انتخاب کاربر یا ادمین، Fixed Lot، درصد ریسک و توقف اضطراری
- نمایش پلن‌ها، اطلاعات پرداخت، ثبت کد پیگیری و تاریخچهٔ پرداخت
- ثبت و مشاهدهٔ تیکت پشتیبانی
- نمای ادمین برای کاربران، پرداخت‌ها، سیگنال‌ها، تغییر حساب و Audit Log
- عملیات ادمین شامل تمدید، امتیاز، مسدودسازی، تأیید/رد پرداخت و درخواست حساب

## ساخت رابط

```powershell
cd telegram-miniapp
npm ci
npm run build
```

خروجی در `telegram-miniapp/dist` ساخته می‌شود و FastAPI آن را روی مسیر `/miniapp/` سرو می‌کند.

## تنظیمات محیط

```env
MINIAPP_URL=https://your-domain.example/miniapp/
BOT_USERNAME=YourBotUsername
MINIAPP_DEV_BYPASS=false
```

در محیط واقعی `MINIAPP_DEV_BYPASS` باید حتماً `false` باشد. مقدار `MINIAPP_URL` باید HTTPS و دامنهٔ عمومی باشد؛ Telegram مینی‌اپ HTTP یا آدرس localhost را برای کاربران واقعی باز نمی‌کند.

## اجرا

```powershell
python -m uvicorn app.autotrade.api:app --host 0.0.0.0 --port 8080
```

پس از تنظیم `MINIAPP_URL`، دکمهٔ ورود به مینی‌اپ در منوی کاربر و ادمین و دستور `/app` ظاهر می‌شود. برای Menu Button ثابت نیز در BotFather از `/setmenubutton` استفاده و همان URL را ثبت کنید.

## Nginx

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

گواهی SSL را پیش از ثبت URL در BotFather فعال کنید. APIهای مینی‌اپ زیر `/api/v1/miniapp` هستند و هر درخواست باید هدر `X-Telegram-Init-Data` معتبر داشته باشد.

## تست محلی

فقط برای پیش‌نمایش توسعه:

```env
MINIAPP_DEV_BYPASS=true
MINIAPP_DEV_USER_ID=990000001
```

سپس `http://127.0.0.1:8080/miniapp/` را باز کنید. این حالت هرگز نباید روی سرور production فعال بماند.

