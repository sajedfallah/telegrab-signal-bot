# NEXUS Telegram Mini App UI v1

این پوشه اولین پروتوتایپ قابل اجرای Mini App برای پروژه NEXUS است.

## ساختار
- `index.html` — صفحات Home, Signals, Subscriptions, Account, Guide, Support
- `styles.css` — Design System تاریک NEXUS و RTL mobile-first
- `app.js` — Navigation، Telegram WebApp SDK، user hydration و hookهای API

## اصول UX
- Home ساده و مناسب کاربر جدید است.
- Home شامل EA/MT5/License status یا Products نیست.
- Public Channel در Home قرار می‌گیرد.
- Signals فقط Free Signal Channel و VIP Signal Channel را نمایش می‌دهد.
- Subscription و My Account صفحات مستقل دارند.
- اطلاعات AutoTrade/License در Account و flowهای اختصاصی قرار می‌گیرند.

## اتصال بعدی به backend
مقادیر `window.NEXUS_CONFIG` باید از environment/runtime تولید شوند:

```js
window.NEXUS_CONFIG = {
  publicChannelUrl: '...',
  freeSignalUrl: '...',
  supportUrl: '...',
  plansEndpoint: '/api/miniapp/plans'
};
```

در درخواست‌های API، `X-Telegram-Init-Data` ارسال می‌شود. Backend باید `Telegram.WebApp.initData` را سمت سرور validate کند و هیچ entitlement یا user id حساسی را فقط از داده‌ی client اعتماد نکند.

## Preview محلی
از داخل ریشه پروژه یک static server اجرا کنید، برای مثال:

```powershell
python -m http.server 8088 --directory miniapp
```

سپس `http://127.0.0.1:8088` را باز کنید. برای اجرای واقعی در Telegram، URL باید HTTPS و در BotFather به عنوان Mini App/Web App ثبت شود.
