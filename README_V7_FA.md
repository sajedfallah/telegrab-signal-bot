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

این نسخه سه توسعه اصلی را روی هسته v6.5 انجام می‌دهد:

## 1. داشبورد تحلیلی سیگنال
از مسیر `پنل ادمین -> Signal Center -> داشبورد تحلیلی` در دسترس است و بازه‌های ۷ روز، ۳۰ روز و کل دوره را نمایش می‌دهد. آمار نمادها، مدل‌های Trailing و مقایسه Free/VIP نیز جداگانه قابل مشاهده است.

## 2. Subscription / License Engine
هر پلن اکنون می‌تواند تعیین کند دسترسی VIP و Auto Trade داشته باشد یا نه. ادمین از `پلن‌ها و قیمت‌ها -> پلن -> دسترسی‌ها و تمدید` این موارد و درصد تخفیف تمدید را تغییر می‌دهد. خرید تأییدشده، دسترسی همان پلن را روی لایسنس ذخیره می‌کند. تمدید زودهنگام روزهای باقی‌مانده را حفظ می‌کند و Upgrade دسترسی جدید را فعال می‌کند.

## 3. Persistent FSM و معماری ماژولار
MemoryStorage حذف شده و Stateهای ربات در `nexus_fsm.db` ذخیره می‌شوند؛ بنابراین Restart عادی ربات جریان نیمه‌تمام پرداخت یا ساخت سیگنال را پاک نمی‌کند. Analytics و Subscription به Router/Service مستقل منتقل شده‌اند و Stateها نیز از main.py جدا شده‌اند.

## نصب ویندوز

```cmd
py -3.11 -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt --timeout 120 --retries 10
python run.py
```

یا:

```cmd
setup_windows.bat
start_windows.bat
```

## تست

```cmd
run_tests.bat
```

فایل `.env` واقعی داخل ZIP قرار نمی‌گیرد. `.env` نسخه خودت را کنار `run.py` کپی کن.


## تغییرات v7.0.1 — Report Card Final
- گزارش روزانه و هفتگی کانال‌ها به یک فلش‌کارت مستقل و بدون کپشن تبدیل شد.
- کریپتو و فارکس در یک کارت واحد اما در دو بخش مجزا نمایش داده می‌شوند.
- سود/زیان کریپتو بر پایه درصد و سود/زیان فارکس بر پایه پیپ محاسبه و نمایش داده می‌شود.
- کانال عمومی و VIP برای هر بازار جداگانه گزارش می‌شوند.
- میانگین زمان معامله از کارت حذف شد.
- نسخه فارسی ابتدا فونت B Yekan نصب‌شده روی Windows را استفاده می‌کند. در صورت نیاز مسیر فونت را با `REPORT_FA_FONT_PATH` مشخص کنید.
- خواندن `.env` با `utf-8-sig` انجام می‌شود تا BOM ویندوز باعث گم‌شدن `BOT_TOKEN` نشود.
