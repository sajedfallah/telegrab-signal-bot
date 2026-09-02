# اجرای NEXUS روی Windows Server

## نصب وابستگی‌ها (فقط بار اول)
```bat
python -m pip install -r requirements.txt
```

## اجرای سریع هر دو سرویس
روی `start_all_windows.bat` دوبار کلیک کنید.

یا دستی:

### پنجره اول
```bat
python run_api.py
```

### پنجره دوم
```bat
python run.py
```

## تست سلامت API
مرورگر سرور:
`http://127.0.0.1:8080/api/v1/autotrade/health`

باید JSON شامل `ok: true` نمایش داده شود.

## بررسی Build
```bat
python validate_build.py
```

## نکته حیاتی برای مشتری MT5
آدرس `127.0.0.1:8080` فقط برای تستی است که MT5 و FastAPI روی یک کامپیوتر باشند.
برای مشتریانی که MT5 روی سیستم خودشان است، قبل از کامپایل EX5 باید مقدار `NEXUS_API_BASE_URL` در
`mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5`
به دامنه HTTPS عمومی سرور NEXUS تغییر کند.
