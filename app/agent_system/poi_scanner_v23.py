from __future__ import annotations

from typing import Any

from .contracts import MarketSnapshot
from .quadrant import derive_daily_quadrant
from .agents.ict import _latest_fvg, _latest_ob


def scan_pois(snapshot: MarketSnapshot) -> list[dict[str, Any]]:
    """Read-only multi-POI context; proximity never confirms an executable setup."""
    if snapshot.data_freshness_ms > 30_000 or snapshot.missing_data or snapshot.bid is None or snapshot.ask is None:
        return []
    price = (float(snapshot.bid) + float(snapshot.ask)) / 2
    candidates: list[dict[str, Any]] = []
    def add(source: str, tf: str, lo: float, hi: float, side: str, priority: int):
        if not (0 < lo < hi):
            return
        distance = max(lo-price, price-hi, 0.0)
        state = "INSIDE" if lo <= price <= hi else ("ABOVE" if price > hi else "BELOW")
        candidates.append({"source":source,"timeframe":tf,"low":lo,"high":hi,
                           "direction":side,"priority":priority,"distance":round(distance, 6),"state":state,
                           "confirmed":False})
    q = derive_daily_quadrant(snapshot.timeframes.get("D1", ()))
    if q:
        add("DAILY_QUADRANT", "D1", q.low, q.high, "BOTH", 100)
    m15 = snapshot.timeframes.get("M15", ())
    if len(m15) >= 20:
        bull,bear = _latest_fvg(m15)
        if bull: add("FVG", "M15", *bull, "LONG", 80)
        if bear: add("FVG", "M15", *bear, "SHORT", 80)
        bull,bear = _latest_ob(m15)
        if bull: add("OB", "M15", *bull, "LONG", 75)
        if bear: add("OB", "M15", *bear, "SHORT", 75)
    m5 = snapshot.timeframes.get("M5", ())
    if len(m5) >= 24:
        # Recent structure reference: proximity context, not an FVG/OB or entry.
        prior=m5[-25:-1]
        low=min(float(x["low"]) for x in prior)
        high=max(float(x["high"]) for x in prior)
        span=max(high-low,0.01)
        epsilon=span * 0.02
        add("SELL_SIDE_LIQUIDITY", "M5", low-epsilon, low+epsilon, "LONG", 40)
        add("BUY_SIDE_LIQUIDITY", "M5", high-epsilon, high+epsilon, "SHORT", 40)
    # Prioritize price-inside and then distance; priority resolves comparable distances.
    candidates.sort(key=lambda p: (p["distance"]>0, p["distance"], -p["priority"]))
    return candidates
