# NEXUS v0.5.8 — Unified Execution Truth

این نسخه لایه گزارش یکپارچه را اضافه می‌کند بدون حذف مسیرهای قدیمی.

- `cycle_id` برای جدا کردن چرخه‌های معاملاتی
- Execution ledger شامل gross P/L، commission، swap، slippage، risk cash، realized R، position ID و deal ID
- MT5 history reconciliation منبع بازیابی در صورت از دست رفتن event
- AutoTrade daily stats از execution ledger استفاده می‌کند
- Signal analytics فقط چرخه جاری را برای گزارش‌های جاری در نظر می‌گیرد
- Break-even trailing قبل از ثبت `be_done` فاصله Stop/Freeze و SL واقعی را بررسی می‌کند
- محاسبات ATR trailing در هر position حداکثر یک بار در ثانیه انجام می‌شود

## منبع حقیقت

Signal Truth = `signals`
Execution Truth = `autotrade_trade_executions` با داده broker/MT5
Final report = reconcile شده بر اساس signal + position/deal
