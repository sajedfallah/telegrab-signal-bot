# NEXUS V7.0.7

## اعلان Auto Trade
- پیام‌های مفصل اجرای معامله حذف شدند.
- کاربر فقط یک اعلان کوتاه دریافت می‌کند.
- اعلان پس از زمان تنظیم‌شده (پیش‌فرض ۸ ثانیه) خودکار حذف می‌شود.
- Command receiptها دیگر پیام جداگانه ایجاد نمی‌کنند.
- جزئیات معامله فقط در وضعیت/معاملات/تاریخچه Auto Trade باقی می‌ماند.

## راهنمای تصویری
مسیر واحد و استاندارد:
`assets/guides/NEXUS_AutoTrade_MT5_Guide.mp4`

## اتصال واقعی صرافی
- انتخاب Binance / Bybit / LBank / KuCoin / OKX / Gate.io / Bitget
- دریافت API Key / Secret / Passphrase از طریق FSM
- حذف پیام‌های حاوی Credential بعد از خواندن
- تست واقعی Authentication از طریق CCXT
- رمزنگاری Credentialها با Fernet قبل از ذخیره در SQLite
- تست مجدد اتصال و Disconnect از داخل Telegram
- یک حساب صرافی برای هر Telegram user

نکته: این نسخه اتصال واقعی و امن صرافی را فراهم می‌کند. Exchange Execution Engine برای باز/بستن خودکار سفارش Crypto یک لایه جداست و در این Build فعال نشده است.
