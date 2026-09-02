# NEXUS v7.0.5 — Broker Symbol Mapping Fix

این Build برای سازگاری Auto Trade با نام‌گذاری متفاوت نمادها در بروکرهای مختلف اصلاح شده است.

## نمونه‌های پشتیبانی‌شده
- `XAUUSD`
- `XAUUSD.EC`
- `XAUUSDm`
- `m.XAUUSD`
- `XAUUSD-pro`
- `GOLD`
- `GOLD.EC`
- و الگوهای مشابه Prefix/Suffix

## تغییر اصلی
Symbol Mapper اکنون تمام نمادهای ارائه‌شده توسط بروکر را بررسی می‌کند، نه فقط Market Watch.
بهترین Match انتخاب، در Market Watch فعال و قابل‌معامله بودن آن بررسی می‌شود.

## نکته
اگر هیچ نماد قابل‌معامله‌ای برای Signal Symbol پیدا نشود، EA معامله را باز نمی‌کند و در Experts Log علت را ثبت می‌کند.
