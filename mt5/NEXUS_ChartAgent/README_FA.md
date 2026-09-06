# NEXUS ChartAgent — Screenshot-only

`NEXUS_ChartAgent.mq5` یک Expert مستقل و صرفاً برای ساخت تصویر نمودار است. این Expert هیچ مسیر معاملاتی ندارد و نباید جایگزین `NEXUS_AutoTrade` شود.

## قرارداد اجرایی

- هر ۲ ثانیه job را از API می‌خواند.
- نمودار اختصاصی باز می‌کند، Entry / SL / همهٔ TPها را در بازهٔ ثابت قرار می‌دهد و تصویر PNG را برمی‌گرداند.
- ممکن است MT5 حین redraw مقدار `CHART_PRICE_MIN/MAX` را موقتاً `0/0` بدهد. Agent فقط تنظیمات قابل‌اعتماد `CHART_SCALEFIX` و `CHART_FIXED_MIN/MAX` را تأیید می‌کند؛ `0/0` به‌تنهایی خطا نیست.
- اگر fixed scale واقعاً تنظیم نشود، خطای deterministic `TRADE_LEVEL_SCALE_VERIFY_FAILED` برمی‌گرداند.

## نصب قالب ایمن

قالب screenshot باید `NEXUS_Screenshot.tpl` نام داشته باشد و در `Profiles\Templates` همان MT5 قرار بگیرد. قالب شخصی تریدر استفاده نمی‌شود.

برای جلوگیری از ورود token یا Expert input به Git، template از repo کپی نمی‌شود. فایل تأییدشده را با guard زیر provision کنید:

```powershell
python scripts\provision_screenshot_template.py `
  --source C:\approved\NEXUS_Screenshot.tpl `
  --destination-dir "C:\...\MQL5\Profiles\Templates"
```

این guard قالب‌های دارای `<expert>`، Admin/API token، password، secret یا credential را رد می‌کند. پس از نصب، یک capture staging بگیرید و فایل یا secret را commit نکنید.

## تنظیمات staging

- `InpApiBaseUrl=http://127.0.0.1:18080`
- `InpPollSeconds=2`
- `InpChartTemplate=NEXUS_Screenshot.tpl`
- `InpAdminToken` فقط در MT5/VPS تنظیم می‌شود و هرگز در سورس یا template قرار نمی‌گیرد.
