# NEXUS — ارسال سیگنال FREE به Topic کامیونیتی

این تغییر، مقصد منطقی `FREE` را در کل NEXUS حفظ می‌کند ولی مقصد فیزیکی تلگرام را به یک Topic مشخص از گروه Forum/Community منتقل می‌کند.

## مسیرهای پوشش‌داده‌شده

- سیگنال صادرشده از پنل ادمین ربات: `FREE` و بخش FREE از `BOTH`
- سیگنال صادرشده از MT5 Admin/Expert: `destination=FREE` و بخش FREE از `BOTH`
- پیام اولیه سیگنال (تصویر + کپشن)
- Replyهای چرخه معامله مثل TP / SL / BE / Manual Close / Trailing Exit
- هر ارسال دیگری که در کد فعلی به مقصد منطقی FREE فرستاده می‌شود

VIP بدون تغییر باقی می‌ماند.

## نکته معماری MT5

داخل Expert هیچ `chat_id` یا `message_thread_id` تلگرام ذخیره نمی‌شود. Expert فقط مقصد منطقی `FREE | VIP | BOTH` را به Backend می‌دهد. Backend/Telegram runtime مسئول تبدیل `FREE` به Community Topic است. این جداسازی باعث می‌شود با تغییر Topic نیازی به Compile و توزیع EX5 جدید نباشد.

## پیدا کردن Chat ID و Topic ID

1. ربات NEXUS را در `nexus community` ادمین کنید.
2. وارد Topic موردنظر، مثلاً `سیگنال` شوید.
3. داخل همان Topic بفرستید:

   `/topicid`

   یا:

   `/setfreetopic`

4. ربات دو مقدار زیر را برمی‌گرداند:

   `FREE_SIGNAL_CHAT_ID=-100...`

   `FREE_SIGNAL_TOPIC_ID=...`

## تنظیم VPS

دو مقدار را به `.env` اضافه کنید:

```env
FREE_SIGNAL_CHAT_ID=-1001234567890
FREE_SIGNAL_TOPIC_ID=123
```

بعد هر دو سرویس را Restart کنید:

- `NEXUS-Telegram-Bot`
- `NEXUS-AutoTrade-API`

## رفتار سازگاری

اگر یکی از دو متغیر بالا خالی باشد، Topic routing غیرفعال است و سیستم دقیقاً مثل قبل از `FREE_CHANNEL_ID` / `FREE_CHANNEL_URL` استفاده می‌کند.

وقتی Topic routing فعال باشد، `FREE_CHANNEL_ID` و `FREE_CHANNEL_URL` همچنان به عنوان alias منطقی FREE باقی می‌مانند، اما تماس‌های Bot API برای مقصد FREE به `FREE_SIGNAL_CHAT_ID + FREE_SIGNAL_TOPIC_ID` هدایت می‌شوند.

## تست نهایی

1. از پنل ربات یک Signal با مقصد `FREE` صادر کنید؛ باید در Topic سیگنال ظاهر شود.
2. از Expert ادمین یک Signal با مقصد `FREE` صادر کنید؛ بعد از Execution Gate باید در همان Topic ظاهر شود.
3. یک Signal با مقصد `BOTH` صادر کنید؛ FREE باید در Topic و VIP در کانال VIP منتشر شود.
4. TP/SL/Close را تست کنید؛ Reply باید زیر همان پست سیگنال در همان Topic ثبت شود.
