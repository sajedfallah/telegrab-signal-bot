# NEXUS v0.6.5 — گزارش بررسی جامع عدم ارسال Reply نتیجه پوزیشن بسته‌شده

## نتیجه اجرایی

علت اصلی با اطمینان بالا شناسایی شد: مسیر `history-reconcile` می‌تواند حقیقت بسته‌شدن معامله را از بروکر دریافت کرده و Signal را `CLOSED` کند، در حالی که این مسیر عمداً هیچ پیام Telegram منتشر نمی‌کند. اگر رویداد event-driven `CLOSE` بعد از آن توسط worker پردازش شود، handler فعلی به‌دلیل `status == CLOSED` زودتر `return` می‌کند. در نتیجه notification به‌عنوان پردازش‌شده علامت می‌خورد ولی Reply نتیجه هرگز ارسال نمی‌شود.

ترتیب معیوب:

`Broker CLOSE -> history reconcile -> signal CLOSED (no Telegram) -> queued CLOSE -> early return -> notification sent -> result reply lost`

## اصلاح P0 روی این branch

فایل `app/autotrade/history_reconcile_guard.py` یک bridge سازگار با معماری فعلی اضافه می‌کند:

1. broker reconciliation همچنان حقیقت اجرای معامله را ثبت می‌کند؛
2. اگر CLOSE واقعی هنوز Telegram message id ندارد، Signal از `CLOSED` به `CLOSING` منتقل می‌شود؛
3. CLOSE با همان `event_id` وارد صف durable موجود می‌شود؛
4. `CLOSING` در polling سیگنال جدید دیده نمی‌شود چون AutoTrade فقط `ACTIVE` را poll می‌کند؛
5. worker عادی نتیجه را به Signal اصلی Reply می‌کند؛
6. اگر Telegram خطا دهد، notification claim آزاد می‌شود و retry می‌شود؛
7. فقط بعد از موفقیت reply، مسیر عادی Signal را نهایی `CLOSED` می‌کند.

Idempotency حفظ شده است: re-reconcile همان CLOSE، notification جدید با event key تکراری نمی‌سازد و اگر `MT5_CLOSE/CLOSE` با Telegram message id قبلاً ثبت شده باشد هیچ recovery جدیدی queue نمی‌شود.

## بررسی اجزای درخواست‌شده

### 1. لاگ‌ها

Runtime log در `logs/nexus.log` نوشته می‌شود. خود فایل runtime عمداً داخل GitHub نیست؛ بنابراین لاگ واقعی سرور از repository قابل مشاهده نیست. ابزار `scripts/diagnose_close_reply.py` اضافه شد تا آخرین خطوط مربوط به `CLOSE`, `MT5_EVENT`, `SIGNAL_ANCHOR`, `Telegram`, `BadRequest`, `Forbidden`, `RetryAfter` و `text result reply failed` را استخراج کند.

### 2. Channel ID و دسترسی Bot

- FREE از `FREE_CHANNEL_ID` استفاده می‌کند؛ اگر خالی باشد، target از `FREE_CHANNEL_URL` استخراج می‌شود.
- برای FREE private channel، `FREE_CHANNEL_ID` اجباری است.
- VIP مستقیماً از `VIP_CHANNEL_ID` استفاده می‌کند.

ابزار diagnostic با `get_chat` و `get_chat_member` بررسی می‌کند که Bot واقعاً عضو/ادمین کانال باشد و `can_post_messages` داشته باشد.

### 3. Token

ابزار فقط `get_me()` اجرا می‌کند و Token را چاپ نمی‌کند. Invalid/revoked Token یا عدم دسترسی API صریحاً گزارش می‌شود. به‌دلیل سابقه مشاهده Token در یک خروجی تصویری، Token production باید قبل از Release rotate شده باشد.

### 4. تابع Reply

مسیر واقعی:

`autotrade_notification_worker -> _process_mt5_trade_event -> CLOSE -> _publish_result_with_fallback -> _publish_result_to_channel -> bot.send_message(... ReplyParameters(message_id=...))`

تابع fallback ابتدا `*_last_message_id` سپس message id اصلی Signal را امتحان می‌کند و خطا را log می‌کند.

### 5. داده CLOSE

`HistoryReconcileItem/TradeEventRequest` داده‌های کافی را دارند: ticket, signal_id, symbol, direction, volume, entry/SL/TP, exit_price, profit, event_id, event_time, position/deal/cycle IDs و destination. `exit_price <= 0` در CLOSE رد می‌شود. مشکل اصلی کمبود داده نبود؛ ترتیب state transition بود.

### 6. Race condition

P0 تأییدشده همان reconciliation-first race است و روی branch اصلاح شده است.

دو ریسک دیگر در source فعلی main باقی می‌مانند:

- برای `destination=BOTH`، اگر فقط یکی از FREE/VIP موفق شود، کد فعلی Signal را CLOSED می‌کند. کانال ناموفق retry تضمین‌شده ندارد.
- anchor recovery فقط زمانی اجرا می‌شود که هر دو `free_message_id` و `vip_message_id` خالی باشند. اگر فقط anchor یکی از کانال‌های موردنیاز گم شده باشد، recovery اجرا نمی‌شود.

برای merge نهایی توصیه می‌شود success criterion به «تمام destinationهای موردنیاز موفق شده‌اند» تغییر کند و anchor recovery per-channel شود.

### 7. Queue

صف durable موجود است (`autotrade_notifications`). در exception، worker claim را release می‌کند تا retry شود. مشکل P0 این بود که `status=CLOSED -> return` exception نبود و worker notification را sent علامت می‌زد؛ بنابراین retry هیچ‌وقت رخ نمی‌داد. اصلاح جدید این silent-success را برای history-reconciled CLOSE حذف می‌کند.

## اولویت ریسک‌ها

| اولویت | مشکل | احتمال | اثر | وضعیت |
|---|---|---:|---:|---|
| P0 | History reconcile قبل از CLOSE worker و early-return روی CLOSED | بسیار بالا | از دست رفتن کامل Reply | اصلاح شده روی branch |
| P1 | BOTH: یک کانال موفق = final CLOSED | متوسط تا بالا | Reply یکی از کانال‌ها گم می‌شود | نیازمند hardening نهایی |
| P1 | Recovery فقط وقتی هر دو anchor خالی‌اند | متوسط | یک channel anchor قابل بازیابی نیست | نیازمند hardening نهایی |
| P1 | Channel ID / bot admin / can_post_messages اشتباه | متوسط | تمام ارسال‌های یک کانال fail | diagnostic اضافه شد |
| P1 | Invalid/revoked/old Bot Token | متوسط | تمام Telegram API fail | diagnostic اضافه شد؛ rotation الزامی |
| P2 | Signal/ticket mapping پیدا نشود و event stale تلقی شود | پایین تا متوسط | CLOSE بدون lifecycle delivery | نیازمند log/runtime verification |
| P2 | Telegram timeout/rate limit | پایین تا متوسط | تأخیر/Retry | queue retry موجود؛ backoff قابل بهبود |
| P3 | dynamic HTML characters در payload | پایین | Telegram BadRequest | در صورت مشاهده log باید escape سخت‌گیرانه شود |

## تست‌های اضافه‌شده

`tests/test_mt5_history_reconciliation.py` اکنون پوشش می‌دهد:

- CLOSE reconciliation نتیجه broker را ثبت ولی تا delivery موفق در `CLOSING` نگه دارد؛
- recovery دقیقاً یک notification queue کند؛
- retry/reconcile تکراری duplicate نسازد؛
- اگر Reply واقعی قبلاً message id دارد recovery دوباره ساخته نشود؛
- OPEN reconciliation رفتار قبلی را حفظ کند.

CI branch همچنین compileall، regression هدفمند و full pytest را اجرا می‌کند.

## تست Runtime روی سرور

از root پروژه با همان `.env` واقعی اجرا شود:

`python scripts/diagnose_close_reply.py`

خروجی باید Bot identity، FREE/VIP target، permission status، Signalهای CLOSED/CLOSING بدون Reply و لاگ‌های مرتبط را نشان دهد؛ هیچ secret چاپ نمی‌شود.
