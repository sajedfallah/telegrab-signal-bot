# مهاجرت NEXUS v0.5.8 به v0.6.0

این نسخه **rollback point** نسخه 0.5.8 را حفظ می‌کند و دیتابیس را با migration خودکار ارتقا می‌دهد.

### قبل از اجرا
- از `nexus_bot.db` و `nexus_fsm.db` نسخه پشتیبان بگیرید.
- فایل `.env` را از نسخه فعال کپی کنید؛ داخل ZIP انتشار قرار ندهید.
- سرویس‌های قبلی را تا پایان تست Demo متوقف نکنید.

### تغییر معماری
`MT5 Admin → API → MT5 Clients → Broker`

Telegram دیگر مجاز به ساخت، تغییر، لغو یا بستن Signal نیست.

### Admin MT5
در تب `SIGNAL`، فیلدهای Symbol/Entry/SL/TP1/Risk را پر کنید، BUY/SELL و MARKET/LIMIT را انتخاب کنید و `ISSUE SIGNAL` را بزنید.

### بررسی سلامت
- `GET /api/v1/autotrade/health` باید HTTP 200 بدهد.
- تست‌ها باید سبز باشند.
- در EA تب SIGNAL باید `AUTHORITY MT5 ADMIN ONLY` دیده شود.
- در Client EA باید Signal Cursor جلو برود و `RECEIVED/EXECUTED` ثبت شود.
