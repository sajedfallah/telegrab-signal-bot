# NEXUS v0.6.5 — Broker Truth / Recoverable Delivery / Verified MT5 Build

## اجرای Backend
```cmd
.venv\Scripts\activate
python -m pytest -q
".venv\Scripts\python.exe" run_api.py
```

Health: `http://127.0.0.1:8080/api/v1/autotrade/health` باید `version=0.6.5` بدهد.

## Fresh Start
`RESET_VNEXT_DB.bat` را اجرا کنید. فایل `.env` را حذف نکنید. اولین Signal از DB تازه `NX-0001` خواهد بود.

## MT5
فایل `mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5` را در MetaEditor باز و Compile کنید.

### Live Sync
EA هر 5 ثانیه Snapshot Position/Order را به Backend می‌فرستد. Telegram Admin Live Center فقط همین وضعیت broker-confirmed را نمایش می‌دهد.

### Publication Gate
- `executed` / `pending` → اجازه انتشار Signal اصلی + Screenshot
- `rejected` / `failed` / `failed_retryable` → بدون انتشار Signal و بدون Screenshot
- lifecycle بعدی → فقط متن/Reply و بدون Screenshot
