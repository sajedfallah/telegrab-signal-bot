# Optional TradingView screenshot capture (Agent Test only)

TradingView provides a **visual reference**, not broker-executable prices.
NEXUS MT5 remains authoritative for OHLC, Bid/Ask, POIs, ICT validation and signals.

## Install on the isolated Windows test clone

```powershell
cd C:\NEXUS_AGENT_TEST
python -m pip install "playwright>=1.50,<2"
python -m playwright install chromium
```

Set Windows User environment variables:

```powershell
[Environment]::SetEnvironmentVariable("NEXUS_AGENT_CHART_SOURCE","TRADINGVIEW","User")
[Environment]::SetEnvironmentVariable("NEXUS_AGENT_TV_SYMBOL","OANDA:XAUUSD","User")
```

Reload those environment variables into a **new** PowerShell session before starting the unified runtime.

Run `/analysis M1` in the bot's private chat. When TradingView capture succeeds, Telegram receives an **unannotated TradingView reference screenshot**, with an MT5-derived checklist. If capture fails, the original MT5 chart renderer is used automatically.

## Strict non-goals for this phase

- Do NOT overlay MT5 zones onto TradingView pixels without a tested candle-time and price-axis transformation.
- Do NOT assert that TradingView OANDA:XAUUSD and the broker's MT5 XAUUSD are the same feed.
- No OpenAI-generated prices, candles or image labels.
- No trading or order execution.
- Do not put TradingView credentials in source or bot messages.
- Website availability, layouts and usage policies can change; this capture must remain optional.

Rollback instantly:

```powershell
[Environment]::SetEnvironmentVariable("NEXUS_AGENT_CHART_SOURCE","MT5","User")
```

Restart the **test** agent process only. Never touch production services.
