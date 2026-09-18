# NEXUS Telegram Mini App

Status: **Production**  
Canonical URL: https://telegrab-signal-bot.vercel.app/  
Vercel Root Directory: `miniapp`

## Architecture

The Mini App is a static frontend hosted by Vercel. Protected business logic and Telegram authentication stay on the VPS.

```text
Vercel frontend
  /miniapp/api/*
        |
        v
https://api.nexustrade.ir/miniapp/api/*
```

The rewrite is defined in `vercel.json`.

## Main views

- Landing
- Home
- Signals
- Live Charts
- Plans / subscriptions
- Account
- supporting performance, trade, payment and purchase flows

Live Charts use the NEXUS/MT5 market feed. Gold/Forex prices are not synthesized in the frontend.

## Telegram authentication

Frontend API requests attach `Telegram.WebApp.initData` as `X-Telegram-Init-Data`. The VPS validates the Telegram HMAC signature, timestamp and user before protected routes return data.

A normal desktop browser does not provide Telegram `initData`; therefore authenticated Home/Signals/Plans/Account API calls may return 401 outside Telegram. Public chart endpoints can still work in a browser.

## Development

UI-only local server:

```bash
python -m http.server 8088 --directory miniapp
```

For authenticated end-to-end testing, open the Vercel PR Preview from Telegram.

## Deployment

- Git branch / PR -> automatic Vercel Preview.
- `main` -> automatic Vercel Production.
- Canonical Production URL -> https://telegrab-signal-bot.vercel.app/
- Vercel project -> `telegrab-signal-bot`.
- Root Directory -> `miniapp`.

Do not store bot tokens, broker credentials or VPS runtime secrets in the frontend or Vercel project.
