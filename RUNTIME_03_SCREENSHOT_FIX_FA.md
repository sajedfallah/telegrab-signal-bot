# NEXUS v0.6.0 — Runtime-03 Screenshot Fix

## وضعیت
- MT5 execution: verified by user; position opened successfully.
- Telegram publication: verified; signal is delivered, but the chart area was blank/black.

## علت
`CaptureChartBase64()` was called with the canonical symbol (`XAUUSD`) while the host chart was broker-specific (`XAUUSD.ec`). The previous lookup could select another chart or fail to select the host chart. A screenshot of the wrong/blank chart could therefore be published.

## اصلاح
1. If the requested canonical symbol matches the host chart canonical symbol, always capture `ChartID()` first.
2. Otherwise resolve the requested symbol through `CNexusSymbolMapper` before scanning charts.
3. Prefer the resolved broker symbol on the trailing timeframe, then any timeframe.
4. Add canonical-match fallback for unusual broker aliases.
5. Log the exact screenshot source (`chart_id`, broker symbol, period, canonical symbol).
6. Wait for chart repaint after hiding NEXUS UI objects.
7. Reject suspiciously tiny screenshot files/base64 payloads.

## Expected log
`NEXUS screenshot source: chart_id=... broker_symbol=XAUUSD.ec period=PERIOD_M15 canonical=XAUUSD`

followed by:
`NEXUS screenshot captured: bytes=... base64_chars=...`

## Validation
Selected runtime tests: **21 passed**.

MQL5 compilation must still be performed in the user's MetaEditor/MT5 terminal.
