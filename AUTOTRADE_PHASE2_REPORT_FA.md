# گزارش NEXUS Auto Trade — Phase 2

این فاز سورس MT5 را به Backend فاز اول متصل می‌کند.

## اضافه‌شده

- `mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5`
- `mt5/NEXUS_AutoTrade/Include/NexusTypes.mqh`
- `mt5/NEXUS_AutoTrade/Include/JsonLite.mqh`
- `mt5/NEXUS_AutoTrade/Include/APIClient.mqh`
- `mt5/NEXUS_AutoTrade/Include/SignalParser.mqh`
- `mt5/NEXUS_AutoTrade/Include/SymbolMapper.mqh`
- `mt5/NEXUS_AutoTrade/Include/RiskManager.mqh`
- `mt5/NEXUS_AutoTrade/Include/TradeManager.mqh`
- `mt5/NEXUS_AutoTrade/Include/TrailingEngine.mqh`
- `mt5/NEXUS_AutoTrade/Include/CommandManager.mqh`

## جریان اجرا

Telegram Bot → NEXUS DB → FastAPI → MT5 EA → Broker

شبکه در `OnTimer` Poll می‌شود و Trailing محلی در `OnTick` اجرا می‌شود تا WebRequest روی هر Tick انجام نشود.

## مرحله بعد از این Build

1. Compile سورس در MetaEditor.
2. رفع هر خطای Compiler وابسته به Build متاتریدر.
3. اجرای Acceptance Test روی حساب Demo.
4. تست Open / Reject / Break Even / Partial / SL / TP / Close.
5. تست جداگانه ۷ مدل Trailing.
6. پس از پایدار شدن، ساخت EX5 Release.

## Update v0.3.0 - On-chart Setup Wizard
- License Key از Inputs کاربر حذف شد و از پنل روی چارت دریافت می‌شود.
- مدیریت سرمایه، Risk % و Fixed Lot از پنل روی چارت قابل انتخاب است.
- تنظیمات کاربر پس از فعال‌سازی ذخیره و در اجرای بعدی بازیابی می‌شود.
- API URL داخلی و ثابت است: http://127.0.0.1:8080
- در نبود تنظیمات، EA روی چارت باقی می‌ماند و Setup Wizard نمایش می‌دهد.
