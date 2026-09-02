# منوی «معرفی و راهنما»

در داشبورد اصلی کاربر گزینه `🎓 معرفی و راهنما` اضافه شده است.

کلیپ‌ها در صورت قرار گرفتن فایل MP4 روی سرور مستقیماً با Telegram `send_video` در چت نمایش داده می‌شوند؛ کاربر تصویر بندانگشتی و دکمه Play می‌بیند و می‌تواند ویدیو را داخل Telegram پخش کند.

مسیر فایل‌ها:
- `assets/guides/NEXUS_Intro.mp4`
- `assets/guides/NEXUS_Purchase_Guide.mp4`
- `assets/guides/NEXUS_AutoTrade_MT5_Guide.mp4`
- `assets/guides/NEXUS_AutoTrade_Crypto_Guide.mp4`

اگر فایل محلی موجود نباشد، می‌توان URL ویدیو را در `.env` قرار داد:
- `GUIDE_INTRO_VIDEO_URL`
- `GUIDE_PURCHASE_VIDEO_URL`
- `GUIDE_MT5_VIDEO_URL`
- `GUIDE_CRYPTO_VIDEO_URL`

بعد از ارسال هر کلیپ، داشبورد راهنما دوباره به عنوان آخرین پیام چت ارسال می‌شود.
