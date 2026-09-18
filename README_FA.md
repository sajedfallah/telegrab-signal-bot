# NEXUS

## NEXUS ICT Expert V22.46 — Deep Research Telemetry + Analytics Viewer

نسخه فعلی Companion Expert track: **V22.46**.

تمرکز فعلی:
- Daily CE / Quadrant-aware signal quality.
- Reversal / Continuation + Market Regime.
- Parent/Reply Telegram lifecycle.
- Execution reject transparency.
- R-Multiple / MFE / MAE analytics.
- CE vs No-CE و CE50 vs CE75 attribution.
- Deep Signal Snapshot + Lifecycle + Telegram Delivery datasets.
- ثبت ستاپ‌های Armed / Invalidated / Expired برای جلوگیری از Survivorship Bias.
- Deep Research برای CE25/50/75، کیفیت Wick، Touch count و Sequence timing.
- Post-signal horizons در 1/3/5/10/20 کندل با Return R و path MFE/MAE.
- Counterfactual management برای مقایسه Trail07 با TP/BE جایگزین.
- Analytics Viewer با UI مبتنی بر Mosaic Lite / Cruip.

**V22.46 هیچ فیلتر جدیدی برای صدور Signal اضافه نمی‌کند.** داده‌ها فقط برای تحلیل آینده جمع می‌شوند.

مستندات جدید:
- [Evolution V22.32 → V22.42](docs/releases/NEXUS_ICT_V22_32_TO_V22_42_FA.md)
- [V22.44 → V22.46 Release](docs/releases/NEXUS_ICT_V22_44_TO_V22_46_FA.md)
- [V22.46 Deep Research Schema](docs/analytics/NEXUS_ICT_V22_46_DEEP_RESEARCH_SCHEMA_FA.md)
- [V22.46 Analytics Viewer / Mosaic UI](docs/analytics/NEXUS_ICT_V22_46_VIEWER_MOSAIC_UI_FA.md)
- [V22.42 Telemetry Schema](docs/analytics/NEXUS_ICT_V22_42_TELEMETRY_SCHEMA_FA.md)
- [V22.31 Trail07 Release](docs/releases/NEXUS_ICT_V22_31_FA.md)
- [V22.31 Runbook](docs/wiki/NEXUS_ICT_V22_31_RUNBOOK_FA.md)
- Tracking: #47, #50
- PR: #48

> Security: Private server MQ5 source شامل runtime credential است و عمداً در GitHub عمومی قرار نمی‌گیرد.

> QA: Static checks ثبت شده‌اند؛ MetaEditor compile و Demo forward-test هنوز قبل از Production لازم‌اند.

---

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
