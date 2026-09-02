# NEXUS v0.6.0 — Runtime Improvements Pack 02

## Scope
این بسته بر پایه آخرین سورس `NEXUS_v0.6.0_FIXED(2)` ساخته شده و سه مشکل عملی مشاهده‌شده در تست MT5 را هدف می‌گیرد:

1. شناسایی خودکار نماد چارت میزبان و تبدیل نماد بروکر به نماد canonical برای Signal.
2. اجرای مستقیم Signal ادمین از پاسخ canonical ایجادشده، برای جلوگیری از skip شدن Signal به‌علت cursor قدیمی؛ به‌همراه diagnostics کامل قبل و بعد از ارسال سفارش.
3. بازطراحی پنل ادمین به ساختار دو سطحی `SIGNAL` و `SETTINGS / MANAGEMENT` و فشرده‌سازی فضای پنل.

## MT5 fixes
- `g_admin_signal_symbol` دیگر با `XAUUSD` hard-code نمی‌شود؛ در `OnInit` و تغییر چارت از `_Symbol` sync می‌شود.
- `CanonicalSignalSymbol()` برای نمادهای رایج و suffix/prefixهای بروکر canonicalization انجام می‌دهد.
- مسیر `IssueAdminSignal()` اکنون ترتیب آرگومان‌های `response, chart_base64` را مطابق قرارداد `APIClient.mqh` ارسال می‌کند.
- بعد از ایجاد Signal، EA همان `signal` object موجود در پاسخ POST را parse و مستقیماً وارد `ProcessIncomingSignal()` می‌کند؛ بنابراین `g_last_signal_id` قدیمی نمی‌تواند Signal جدید ادمین را skip کند.
- Signal execution اکنون diagnostics مربوط به terminal trading permission، symbol trade mode، volume، margin، stop distance و broker preflight را ثبت می‌کند.
- خطای sizing زیر حداقل حجم بروکر با balance/risk/loss-per-lot/min/step به‌صورت صریح در Experts ثبت می‌شود.
- Admin Signal UI دارای `RISK/FIXED` sizing و fixed-lot field است تا برای smoke test با حداقل حجم مجاز، نیازی به دستکاری کد نباشد.
- پنل اصلی دو سطح دارد: `SIGNAL` و `SETTINGS / MANAGEMENT`؛ تنظیمات Connection/Trading/Risk/System در زیرمنوی دوم باقی می‌مانند.
- پنل Signal فشرده‌تر شده و اطلاعات host/canonical symbol، sizing، delivery و trade management را دسته‌بندی می‌کند.
- پنل با عرض چارت تطبیق نسبی دارد و دکمه‌ها/کنترل‌ها Z-order مناسب دارند.

## Safety
- Risk sizing در صورت کمتر بودن حجم محاسبه‌شده از حداقل بروکر، حجم را به‌صورت خودکار به بالا گرد نمی‌کند؛ این کار برای جلوگیری از افزایش ناخواسته ریسک حفظ شده است.
- حالت `FIXED` فقط زمانی اجرا می‌شود که Admin صریحاً آن را انتخاب کرده و `lot_size` معتبر باشد.
- بررسی margin و broker trade mode قبل از ارسال سفارش اضافه شده است.
- خطاهای transient همچنان cursor را مصرف نمی‌کنند.

## Validation
- Python compileall: PASS
- pytest: 182 passed, 3 skipped
- `validate_build.py`: PASS for source/package checks; EX5 compilation remains a MetaEditor-side requirement.
- MQL5 cannot be compiled in this Linux build environment; final compile must be performed in MetaEditor on the target MT5 terminal.

## Smoke-test protocol
برای تست بعدی روی حساب دمو:
- فقط یک EA instance روی یک chart.
- `Algo Trading = ON`.
- WebRequest: `http://127.0.0.1:8080`.
- ابتدا `MARKET`، نه LIMIT.
- برای حذف ابهام sizing، در Signal tab حالت `FIXED` و کمترین `lot` مجاز بروکر انتخاب شود.
- SL/TP معتبر باشند.
- بعد از `ISSUE SIGNAL` در Experts باید این زنجیره دیده شود:
  `ISSUED → RECEIVED → symbol mapping → ENTRY CHECK PASS → MARKET PREFLIGHT → EXECUTED`
  یا یک خطای دقیق مانند `SIZING FAILED`, `insufficient free margin`, `terminal trading is disabled`, `broker symbol trading mode...` یا `trade open failed ... [retcode=...]`.
