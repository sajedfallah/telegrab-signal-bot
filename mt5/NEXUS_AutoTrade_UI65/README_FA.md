# NEXUS AutoTrade UI65 — پورت امن رابط MT5

این پوشه نسخهٔ **UI Candidate** اکسپرت NEXUS را نگه می‌دارد. هدف آن انتقال رابط جدید بدون کپی یا بازنویسی منطق معاملاتی Production است.

## معماری

- `NEXUS_AutoTrade_UI65.mq5` فقط لایهٔ UI و Event Adapter است.
- `NEXUS_AutoTrade.mq5` داخل همین پوشه یک Build Shim کوچک است و Core واقعی را از `../NEXUS_AutoTrade/NEXUS_AutoTrade.mq5` include می‌کند.
- Core Production دست‌نخورده می‌ماند و همچنان مسئول Execution، Live Sync، Receipt Ordering، Multi-instance Guard، Reconciliation، Trailing و Trade Lifecycle است.
- Web Chart Capture همچنان در `../NEXUS_ChartAgent/NEXUS_ChartAgent.mq5` جداست و وارد Tick Path اکسپرت معاملاتی نشده است.

## رابط جدید

### Admin

- `NEW SIGNAL`
- `TRADES`
- `SETTINGS`
- صدور سیگنال: `REVIEW SIGNAL` → `CONFIRM & ISSUE`
- `CLOSE POSITION` و `CANCEL PENDING` دارای تأیید دو مرحله‌ای هستند.

### User

- `OVERVIEW`
- `TRADES` به‌صورت View-only
- `SETTINGS`
- در حالت Customer هیچ فیلد Admin Token نمایش داده نمی‌شود.

## نکتهٔ ایمنی Input

UI روی Timer بازطراحی می‌شود، اما Build Shim فقط در لایهٔ UI از حذف/دeselect شدن Edit فعال جلوگیری می‌کند تا تایپ و Paste در MT5 قطع نشود. این Compatibility Wrapper بعد از Include شدن Core تعریف شده است؛ بنابراین هیچ فراخوانی معاملاتی Production را intercept نمی‌کند.

## Compile

فایل زیر را در MetaEditor کامپایل کنید:

```text
mt5/NEXUS_AutoTrade_UI65/NEXUS_AutoTrade_UI65.mq5
```

تا قبل از Compile موفق با **0 errors** و تست Demo، فایل EX5 تولیدی جایگزین نسخهٔ Production نشود.

## Acceptance قبل از Production

1. MetaEditor: `0 errors`.
2. Customer mode: License قابل Paste و Admin Token نامرئی.
3. Admin mode: اتصال با allow-list + token.
4. NEW SIGNAL: Review → Confirm → اجرای همان Canonical Signal.
5. TRADES: BE / Update SL / Update TP / Trailing.
6. Close/Cancel فقط بعد از Confirm.
7. تایپ در Editها هنگام Timer refresh قطع نشود.
8. Screenshot صدور دستی NEXUS UI را مخفی کند و Chart واقعی را بگیرد.
9. Live Sync و Receipt ordering مطابق Core Production باقی بماند.
10. Demo trade test قبل از هر Cutover روی VPS Production.
