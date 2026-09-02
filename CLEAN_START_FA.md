# شروع کاملاً تمیز NEXUS — Signal #1

این ابزار فقط حافظه عملیاتی/معاملاتی را صفر می‌کند و ساختار اصلی پروژه را تغییر نمی‌دهد.

## Python / Telegram

```cmd
python reset_clean_cycle.py --yes
```

این عملیات:

- همه Signalها را پاک می‌کند.
- Signal ID را دوباره از 1 شروع می‌کند؛ اولین Signal جدید `NX-0001` خواهد بود.
- Signal Targets / Updates را پاک می‌کند.
- MT5 receipts و Trade Execution Ledger را پاک می‌کند.
- Notification Queue و Publication Claims را پاک می‌کند.
- Report Dispatch history را پاک می‌کند تا گزارش‌های جدید از صفر محاسبه شوند.
- FSM Telegram را پاک می‌کند.
- قبل از حذف، از DB و FSM داخل `backups/pre_reset/` نسخه پشتیبان می‌گیرد.

عمداً این موارد حذف نمی‌شوند:

- Users
- Licenses
- Subscription Plans
- Subscriptions / Payments
- MT5 Account Bindings
- Exchange Account Bindings

## MT5

پس از اجرای Python reset، در MetaTrader 5 فایل زیر را به‌عنوان Script اجرا کنید:

`mt5/NEXUS_AutoTrade/NEXUS_Reset_Runtime.mq5`

این Script فقط Global Variableهای NEXUS با Prefixهای `NXS.` و `NXS_` را پاک می‌کند؛ فایل License/User Config را حذف نمی‌کند.

پس از اجرای Script، EA اصلاح‌شده `NEXUS_AutoTrade.mq5` را دوباره Compile کنید و EA جدید را روی Demo اجرا کنید.

## نکته مهم

این reset برای شروع یک چرخه تست جدید است. اگر معامله واقعی باز است، قبل از reset آن را ببندید؛ زیرا پاک‌کردن Ledger باعث می‌شود گزارش داخلی NEXUS دیگر تاریخچه آن معامله را نداشته باشد.
