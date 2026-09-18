# NEXUS Analytics Viewer — V22.43

## محل داده
MT5 Common Files:
`%APPDATA%\\MetaQuotes\\Terminal\\Common\\Files`

فایل‌های مصرفی:
- `NEXUS_V22_43_SIGNAL_SNAPSHOTS_<SYMBOL>_<TF>.csv`
- `NEXUS_V22_43_LIFECYCLE_EVENTS_<SYMBOL>_<TF>.csv`
- `NEXUS_V22_43_TRADE_ANALYTICS_<SYMBOL>_<TF>.csv`
- `NEXUS_V22_43_TELEGRAM_DELIVERY_<SYMBOL>_<TF>.csv`

## هدف
Viewer صرفاً لایه‌ی مشاهده/تحلیل است و هیچ Rule، Weight یا Gate معاملاتی را تغییر نمی‌دهد.

## خروجی‌های اصلی
- Win Rate
- Expectancy R
- Net R / P&L
- Avg MFE / MAE
- CE vs No-CE
- CE50 vs CE75
- Reversal vs Continuation
- New York hour attribution
- execution reject breakdown
- Telegram delivery health

## RTL Telegram
تمام پیام‌های کاربر-facing Telegram در V22.43 فارسی هستند و هر خط با RLM برای نمایش RTL پایدار علامت‌گذاری می‌شود.

## Weekly report
Weekly report از bucketهای هفتگی NY ساخته می‌شود و به همان Telegram destination ارسال می‌شود.
