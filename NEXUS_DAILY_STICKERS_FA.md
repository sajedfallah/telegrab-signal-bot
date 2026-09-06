# NEXUS Daily Telegram Stickers

این ماژول استیکر روزانه NEXUS را به‌صورت خودکار در کانال تلگرام منتشر می‌کند.

## فعال‌سازی

در فایل `.env`:

```env
DAILY_STICKERS_ENABLED=true
DAILY_STICKER_CHANNEL_ID=-1001234567890
DAILY_STICKER_TIME=07:00
DAILY_STICKER_CATCHUP_MINUTES=360
DAILY_STICKER_SILENT=false
```

اگر `DAILY_STICKER_CHANNEL_ID` خالی باشد، `PUBLIC_CHANNEL_ID` استفاده می‌شود. Bot باید در کانال مقصد Admin و دارای مجوز Post Messages باشد.

ساعت بر اساس `TIMEZONE` پروژه است؛ مقدار پیش‌فرض پروژه `Asia/Tehran` است.

## وارد کردن یک Sticker Pack کامل

استیکرهای Pack باید از روز اول تا آخر به ترتیب زمانی داخل Pack قرار گرفته باشند.

1. یکی از استیکرهای Pack را برای Bot بفرستید.
2. روی همان استیکر Reply بزنید.
3. دستور زیر را ارسال کنید:

```text
/daily_sticker_import 2026-08-23 31
```

برای شهریور ۱۴۰۵، `2026-08-23` معادل روز اول ماه است. عدد `31` تعداد استیکرهای تقویمی است. اگر Pack استیکرهای Extra دارد، فقط count مربوط به روزهای تقویمی را وارد کنید.

Bot با `getStickerSet` کل Pack را می‌خواند و `file_id` هر استیکر را در `nexus_daily_stickers.db` ذخیره می‌کند. فایل دیتابیس به‌دلیل الگوی `*.db` وارد Git نمی‌شود.

## ثبت تکی

روی استیکر Reply کنید:

```text
/daily_sticker_set 2026-09-06
```

## کنترل و تست

```text
/daily_sticker_status today
/daily_sticker_send today
/daily_sticker_delete 2026-09-06
/daily_sticker_help
```

`/daily_sticker_send` ارسال دستی/آزمایشی را انجام می‌دهد و همان روز را تحویل‌شده ثبت می‌کند، بنابراین Scheduler دوباره آن را ارسال نمی‌کند.

## جلوگیری از ارسال تکراری

هر تحویل با کلید `(date, channel)` در SQLite ثبت می‌شود. در نتیجه Restart سرویس باعث ارسال دوباره همان استیکر نمی‌شود. اگر سرویس بعد از ساعت برنامه‌ریزی‌شده بالا بیاید، تا محدوده `DAILY_STICKER_CATCHUP_MINUTES` امکان Catch-up دارد.
