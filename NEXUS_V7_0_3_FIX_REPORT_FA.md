# NEXUS CORE v7.0.3 — Fix & Guide Hub

## اصلاحات
- رفع crash منوی VIP به علت tuple شدن text در main.py.
- مقاوم‌سازی screen() در برابر ورودی غیررشته‌ای.
- تغییر screen() به حذف داشبورد قبلی و ارسال داشبورد جدید در انتهای چت، برای ثابت ماندن منو در پایین گفتگو.
- افزودن منوی «معرفی و راهنما» به داشبورد کاربر.
- افزودن چهار جایگاه کلیپ: معرفی، خرید، MT5، Crypto.
- نمایش مستقیم MP4 داخل Telegram با send_video و fallback به URL.
- حفظ منوی راهنما به عنوان آخرین پیام پس از نمایش کلیپ.
- ارتقای FastAPI startup به lifespan و حذف warning deprecated on_event.
- API health version: 0.2.0.

## وضعیت تست
- Python compile check: PASS
- Pytest: PASS
- FastAPI TestClient: PASS

## نکته MT5
سورس MQL5 در mt5/NEXUS_AutoTrade قرار دارد. برای EX5 نهایی باید روی Windows/MetaEditor کامپایل شود. فایل EX5 قدیمی در assets/autotrade/previous مربوط به نسخه قبلی است و نباید به جای سورس جدید به عنوان نسخه نهایی توزیع شود.
