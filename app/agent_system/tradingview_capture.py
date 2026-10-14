"""Optional TradingView chart screenshot capture (visual reference only).

Never infer executable prices or price-coordinate mappings from pixels.
MT5 remains the single source of truth for ICT zones and signals.
"""
from __future__ import annotations

import asyncio
import io
import os

from PIL import Image


class TradingViewCaptureError(RuntimeError):
    pass


def _tv_interval(timeframe: str) -> str:
    allowed = {"M1": "1", "M5": "5", "M15": "15", "H1": "60",
               "D1": "D", "W1": "W", "MN1": "M"}
    if timeframe not in allowed:
        raise TradingViewCaptureError("unsupported_timeframe")
    return allowed[timeframe]


async def capture_tradingview_chart(symbol: str, timeframe: str) -> bytes:
    """Return raw chart PNG, without unaudited ICT overlays.

    Requires playwright + installed chromium browser on the test host.
    This feature is opt-in and intentionally has no access to trading accounts.
    """
    if os.getenv("NEXUS_AGENT_CHART_SOURCE", "MT5").upper() != "TRADINGVIEW":
        raise TradingViewCaptureError("tradingview_not_enabled")
    if symbol != "XAUUSD":
        raise TradingViewCaptureError("tradingview_symbol_not_configured")
    tv_symbol = os.getenv("NEXUS_AGENT_TV_SYMBOL", "OANDA:XAUUSD").strip()
    if tv_symbol != "OANDA:XAUUSD" and not (
        tv_symbol.endswith(":XAUUSD") and tv_symbol.split(":")[0].replace("_", "").isalnum()
    ):
        raise TradingViewCaptureError("invalid_tv_symbol")
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise TradingViewCaptureError("playwright_not_installed") from exc

    # chart widget provides a stable compact chart frame without depending on a
    # logged-in user layout. Capture is only a visual reference, not MT5 candles.
    url = (
        "https://s.tradingview.com/widgetembed/"
        f"?symbol={tv_symbol.replace(':', '%3A')}&interval={_tv_interval(timeframe)}"
        "&theme=dark&style=1&hide_top_toolbar=1&hide_legend=0"
        "&saveimage=0&withdateranges=0&allow_symbol_change=0"
    )
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
            response = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            if response is None or response.status >= 400:
                raise TradingViewCaptureError("tradingview_http_error")
            await page.wait_for_timeout(3500)
            visible_text = (await page.locator("body").inner_text(timeout=3000)).lower()
            if any(error in visible_text for error in (
                "403 error", "request could not be satisfied",
                "request blocked", "access denied", "502 bad gateway",
            )):
                raise TradingViewCaptureError("tradingview_error_page")
            png = await page.screenshot(full_page=False, timeout=12000)
        finally:
            await browser.close()
    with Image.open(io.BytesIO(png)) as image:
        if image.size[0] < 1000 or image.size[1] < 500:
            raise TradingViewCaptureError("capture_dimensions_invalid")
        image.verify()
    return png
