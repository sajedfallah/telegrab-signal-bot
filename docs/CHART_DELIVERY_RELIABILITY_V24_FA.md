# NEXUS Chart Delivery Reliability V24

## هدف

این نسخه فقط مسیر تولید/تحویل تصویر سیگنال‌های `WEB_ADMIN` (مینی‌اپ ادمین) را سخت‌گیری می‌کند و به منطق اجرای معامله، T05/T07، تریلینگ و Customer AutoTrade دست نمی‌زند.

زنجیره مورد انتظار:

`Mini App → broker execution receipt → chart capture job → NEXUS_ChartAgent → PNG upload → flash-card renderer → Telegram publication`

## ریشه‌های فنی اثبات‌شده

1. **False range failure در MT5**: بلافاصله بعد از `CHART_SCALEFIX`، ترمینال می‌تواند `CHART_PRICE_MIN/MAX = 0/0` برگرداند. نسخه قبلی این حالت موقت را failure نهایی تلقی می‌کرد و خطای `RANGE_VERIFY_FAILED` می‌داد.
2. **Rate-limit collision**: poll دوثانیه‌ای `/next` و POSTهای `/result`/`/fail` از یک bucket مشترک account استفاده می‌کردند. poll می‌توانست ظرفیت POST را مصرف کند و نتیجه با `HTTP 429` از دست برود.
3. **Transient upload failure**: ChartAgent برای `429/502/503/504` روی result/fail retry درون‌درخواستی نداشت و بعد از تولید موفق PNG نیز ممکن بود upload از دست برود.
4. **Fallback بدون repair**: اگر placeholder با `MT5 CHART UNAVAILABLE` منتشر می‌شد، رسیدن دیرهنگام PNG پیام Telegram موجود را جایگزین نمی‌کرد. وجود `free_message_id/vip_message_id` باعث می‌شد publication idempotency از ارسال دوباره جلوگیری کند، اما media نیز repair نمی‌شد.
5. **DRAFT-only claim بعد از fallback**: انتشار fallback سیگنال `WEB_ADMIN` را `ACTIVE` می‌کند، در حالی‌که claim اولیه ChartAgent فقط `DRAFT` را قبول می‌کرد. بنابراین حتی اگر job repair دوباره صف می‌شد، بعد از fallback امکان claim شدن نداشت.

## تغییرات V24

### 1. ChartAgent hardening

`tools/apply_chart_agent_reliability_v24.ps1` به‌صورت deterministic روی سورس ChartAgent اعمال می‌شود و:

- version را به `0.6.5-chart-agent-reliability-v24` تغییر می‌دهد؛
- بعد از fixed scale تا 2.2s redraw/readback انجام می‌دهد؛
- `SCALE_VISIBLE_RANGE_CONFIRMED` و `SCALE_FIXED_RANGE_CONFIRMED` را ثبت می‌کند؛
- اگر fixed scale settle نشد، فقط یک **autoscale واقعی بروکر** را به‌عنوان fallback قبول می‌کند (`SCALE_AUTOSCALE_FALLBACK`)؛ هیچ قیمت ساختگی تولید نمی‌شود؛
- PNGهای بسیار کوچک یا signature نامعتبر را reject می‌کند؛
- POST result/fail را برای transport error و `429/502/503/504` حداکثر 4 بار با exponential backoff تکرار می‌کند؛
- موفقیت upload را با `SCREENSHOT_UPLOAD_CONFIRMED` ثبت می‌کند.

### 2. Backend queue/rate reliability

`app/autotrade/chart_delivery_guard.py` limiter را در runtime به bucket `account:limit` جدا می‌کند. بنابراین poll با limit=60 و result/fail با limit=30 دیگر یک پنجره مشترک ندارند. این همان emergency production fix قبلی را به‌صورت versioned و قابل تکرار وارد runtime می‌کند، بدون overwrite کردن `app/autotrade/api.py` تولیدی.

### 3. Stateful repair بعد از fallback

اگر capture به `FAILED/EXPIRED` برسد ولی execution receipt معتبر باشد:

- حداکثر **2 repair cycle** جدید queue می‌شود؛
- اگر fallback قبلاً در Telegram منتشر شده باشد، stage به `PUBLISHED_REPAIR_PENDING` می‌رود؛
- `app/autotrade/chart_repair_claim_runtime.py` اجازه claim مجدد را فقط برای حالت محدود `ACTIVE + Telegram message موجود + broker receipt معتبر` می‌دهد؛ مسیر اولیه `DRAFT` بدون تغییر باقی می‌ماند؛
- وقتی PNG واقعی بعداً برسد، backend به‌جای ساخت پیام تکراری، همان photo message موجود را با `edit_message_media` جایگزین می‌کند؛
- eventهای `CHART_REPAIR_QUEUED`, `CHART_REPAIR_APPLIED`, `CHART_REPAIR_FAILED` ثبت می‌شوند؛
- publication/channel claimهای قبلی همچنان idempotent باقی می‌مانند.

### 4. Monitoring / alerting

Endpoint احراز هویت‌شده:

`GET /api/v1/autotrade/admin/chart-capture/health?minutes=30`

خروجی شامل:

- شمارش jobها بر اساس status؛
- fallback publication count؛
- repair applied count؛
- repair exhausted list؛
- 12 job اخیر با error و publication stage.

اگر در پنجره 10 دقیقه failure/fallback از threshold عبور کند یا repair budget تمام شود، alert ادمین با throttle ده‌دقیقه‌ای queue می‌شود.

ابزار read-only:

`tools/diagnose_chart_delivery_v24.ps1`

این ابزار **هرگز `/chart-capture/next` را صدا نمی‌زند** و بنابراین job را claim یا mutate نمی‌کند.

## Failure codes / evidence

موارد مهم برای مانیتورینگ:

- `TRADE_LEVEL_SCALE_FIT_FAILED:*`
- `RANGE_VERIFY_FAILED`
- `SCREENSHOT_TOO_SMALL_BYTES_*`
- `SCREENSHOT_INVALID_PNG_SIGNATURE`
- `UPLOAD_RESULT_HTTP_RETRY`
- `FAIL_JOB_HTTP_RETRY`
- `HTTP 429/502/503/504`
- `CHART_REPAIR_FAILED`
- `TELEGRAM_PUBLISH_FAILED`

موفقیت سالم باید یکی از این scale markers و سپس upload marker را داشته باشد:

- `SCALE_VISIBLE_RANGE_CONFIRMED`
- `SCALE_FIXED_RANGE_CONFIRMED`
- `SCALE_AUTOSCALE_FALLBACK`
- `SCREENSHOT_UPLOAD_CONFIRMED`
- `Screenshot uploaded. job=...`

## Staging gate — حداقل سناریوها

قبل از Production باید تست‌ها PASS باشند:

1. PNG معتبر پذیرفته و empty/bad signature/too-small/oversized رد شود.
2. poll و result/fail rate buckets جدا باشند.
3. terminal capture repair محدود و bounded باشد؛ loop بی‌نهایت ایجاد نشود.
4. PNG دیرهنگام fallback موجود Telegram را با edit media repair کند، نه پیام duplicate.
5. ChartAgent دارای scale settle + HTTP retry + PNG validation باشد.
6. health endpoint و admin alert نصب شده باشند.
7. diagnostic script read-only باشد.
8. fallback-published `ACTIVE` فقط با Telegram anchor و broker receipt معتبر بتواند repair job را claim کند.
9. Production deploy با staging evidence قفل باشد و `app/autotrade/api.py` را overwrite نکند.

فایل‌های pytest:

- `tests/test_chart_delivery_reliability_v24.py`
- `tests/test_admin_positions_v24.py`
- regression قبلی: `tests/test_market_candles_and_publication_recovery.py`

اسکریپت gate:

`tools/stage_chart_delivery_v24.ps1`

این اسکریپت exact commit را در staging ایزوله archive می‌کند، Python syntax/pytest را اجرا می‌کند، ChartAgent patch را فقط روی staged MQ5 اعمال می‌کند و MetaEditor را ملزم به `0 errors` می‌کند. فقط در صورت PASS فایل evidence برای همان commit تولید می‌شود؛ Production تغییر نمی‌کند.

## Production deploy

Backend/ChartAgent deploy:

`tools/deploy_chart_delivery_v24.ps1`

- بدون evidence همان commit اجرا نمی‌شود؛
- `app/autotrade/api.py` را عمداً کپی نمی‌کند تا emergency hotfix تولیدی overwrite نشود؛
- فقط `NEXUS-AutoTrade-API` را restart می‌کند؛
- Telegram Bot، Trading EA، T05/T07 و MarketFeed را دست نمی‌زند؛
- screenshot-only `NEXUS_ChartAgent` را backup و compile می‌کند.

Admin Positions UI deploy:

`tools/deploy_admin_positions_v24.ps1`

- `admin.html`, `admin-positions-v24.css`, `vazirmatn.css` را targeted deploy می‌کند؛
- cache-bust صریح دارد؛
- هیچ سرویس یا MT5 را restart نمی‌کند.

## Production acceptance

پس از deploy، یک **سیگنال جدید Mini App** لازم است. PASS نهایی فقط وقتی اعلام می‌شود که برای همان signal/job شواهد زیر دیده شوند:

1. execution receipt broker-confirmed؛
2. `POLL_JOB_AVAILABLE`؛
3. scale confirmation marker؛
4. `SCREENSHOT_UPLOAD_CONFIRMED`؛
5. job `UPLOADED/COMPLETED`؛
6. Telegram original signal حاوی chart واقعی باشد، یا اگر fallback قبلاً رفته است `CHART_REPAIR_APPLIED` و media همان پیام repair شود؛
7. health endpoint برای پنجره تست `CRITICAL` نباشد.

## Rollback

Backend V24 additive است: برای rollback فایل‌های backup `chart_delivery_guard.py`, `chart_repair_claim_runtime.py`, `combined_api.py` را برگردانید و فقط `NEXUS-AutoTrade-API` را restart کنید. UI positions نیز static است و با برگرداندن `admin.html`, CSS و `vazirmatn.css` rollback می‌شود.

ChartAgent rollback باید با EX5 backup انجام شود. Trading EA، T05/T07 و MarketFeed در V24 تغییر نمی‌کنند.
