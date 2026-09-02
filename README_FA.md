## v7.1.0 — Current Release

- قیمت سرویس‌ها فقط بر اساس USDT: VIP SIGNAL و AUTO TRADE VIP
- پرداخت USDT یا ریال با نرخ لحظه‌ای USDT/RIAL
- فاکتور ریالی با اعتبار پیش‌فرض 15 دقیقه و قابلیت Override نرخ توسط ادمین
- Upgrade با محاسبه اعتبار روزهای باقی‌مانده
- Setup & Activation: 15 / 15 / 7.5 / 0 USDT
- Subscription / License / Invoice / Payment canonical model
- Hard revoke برای Licenseهای لغوشده Auto Trade
- کنترل Account Number + Broker Server
- فقط Signalهای Published + ACTIVE برای Auto Trade
- TP1 تا TP10 در مسیر Auto Trade
- سیاست پایان اشتراک Auto Trade: A / B / C
- تست خودکار: 63 passed

# NEXUS CORE v7.1.0 — Production Hardening & USDT Pricing

نسخه فعلی هسته ربات NEXUS.

ویژگی‌های اصلی:
- Signal Center کامل با Dynamic TP، Trailing، Break Even، Partial Close، Update SL/TP و Close/Result.
- گزارش روزانه/هفتگی ادمین و کانال‌ها.
- داشبورد تحلیلی سیگنال بر اساس بازه، نماد، مدل Trailing و Free/VIP.
- موتور پلن و لایسنس با دسترسی VIP/Auto Trade، تمدید، Upgrade و تخفیف تمدید.
- پرداخت ریالی/USDT، رفرال/امتیاز، تخفیف، کمپین، Broadcast، CRM و Backup.
- FSM پایدار SQLite؛ Stateهای نیمه‌تمام در Restart عادی از بین نمی‌روند.
- معماری ماژولار جدید با Router/Service/Storage/States جداگانه.

راهنمای کامل: `README_V7_FA.md`
معماری: `ARCHITECTURE_V7.md`


## تغییرات v7.0.1 — Report Card Final
- گزارش روزانه و هفتگی کانال‌ها به یک فلش‌کارت مستقل و بدون کپشن تبدیل شد.
- کریپتو و فارکس در یک کارت واحد اما در دو بخش مجزا نمایش داده می‌شوند.
- سود/زیان کریپتو بر پایه درصد و سود/زیان فارکس بر پایه پیپ محاسبه و نمایش داده می‌شود.
- کانال عمومی و VIP برای هر بازار جداگانه گزارش می‌شوند.
- میانگین زمان معامله از کارت حذف شد.
- نسخه فارسی ابتدا فونت B Yekan نصب‌شده روی Windows را استفاده می‌کند. در صورت نیاز مسیر فونت را با `REPORT_FA_FONT_PATH` مشخص کنید.
- خواندن `.env` با `utf-8-sig` انجام می‌شود تا BOM ویندوز باعث گم‌شدن `BOT_TOKEN` نشود.
