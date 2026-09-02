# NEXUS CORE v7.0.2 — تغییرات نسخه

## پایداری سیگنال و معامله
- قفل انتشار سیگنال در اولین کلیک و جلوگیری از Double Publish در سطح FSM + Lock + Database publish_token.
- Retry روی همان Signal ID برای انتشار ناقص؛ ساخت سیگنال جدید لازم نیست.
- EA از Signal ID برای جلوگیری از اجرای تکراری استفاده می‌کند.
- انتخاب اجباری روش حجم Forex: Risk Management یا Fixed Lot؛ این دو همزمان اجرا نمی‌شوند.

## اشتراک و لایسنس
- پشتیبانی از VIP Only، VIP + Auto Trade و Auto Trade Add-on برای VIP فعال.
- تاریخ انقضای VIP و Auto Trade مستقل شده است.
- همان License Key در تمدید حفظ می‌شود.
- Safe Mode اتوترید بر اساس انقضای خود Auto Trade اعمال می‌شود.

## تجربه کاربری Auto Trade
- داشبورد Auto Trade: وضعیت، معاملات باز، تاریخچه، گزارش امروز، License، دانلود MT5، راهنمای نصب، راهنمای تصویری و Exchange.
- راهنمای تصویری با فایل assets/autotrade/NEXUS_AutoTrade_Guide.mp4 یا AUTOTRADE_GUIDE_VIDEO_URL.
- پیام‌ها و فایل‌های مستقل با بازگرداندن منوی اصلی به انتهای چت همراه می‌شوند.
- اعلان‌های اجرای معامله/رد/فرمان و گزارش روزانه Auto Trade اضافه شده‌اند.

## ادمین و Trailing
- دکمه «راهنمای تریلینگ» در Signal Center ادمین.
- توضیح عملکرد هر 7 پروفایل NEXUS_TRAIL_01 تا NEXUS_TRAIL_07.
- تنظیم Trailing و روش حجم در EA روی NEXUS LOCKED قرار گرفته و از سیگنال ادمین پیروی می‌کند.

## Crypto / Exchange
- ساختار حساب Exchange و راهنمای Trade-only API ایجاد شده است.
- اجرای زنده سفارش صرافی در این نسخه هنوز فعال نشده و باید پس از ساخت و تست Adapterهای صرافی منتشر شود.

## نکته MT5
سورس EA به v0.4.0 ارتقا یافته است. EX5 قبلی v0.3.1 برای جلوگیری از ارسال اشتباه به پوشه previous منتقل شده است. قبل از استفاده تجاری، سورس v0.4.0 را Compile و EX5 جدید را در assets/autotrade قرار دهید.
