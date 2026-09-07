from __future__ import annotations

"""One-time commercial pricing migration for the NEXUS v0.6.5 catalog.

The live purchase UI reads persisted rows from ``subscription_plans`` before it
falls back to ``settings.plans``. Updating the config catalog alone therefore
would not change an already-initialized VPS database. This runtime wraps the
existing default-plan seeder and applies the approved 19-USDT VIP pricing once,
while preserving entitlements and all standalone AutoTrade prices.
"""

import logging
from typing import Any

log = logging.getLogger(__name__)

_MIGRATION_KEY = "commercial_pricing_19usd_v1"

# VIP retains the previous duration-discount curve, rebased from 25 to 19 USDT.
# AutoTrade remains on the existing 5-USDT monthly base.
# Bundles are the exact sum of the corresponding VIP + AutoTrade plan.
_APPROVED_PRICES = {
    "VIP1M": "19",
    "VIP3M": "52",
    "VIP6M": "98",
    "VIP12M": "182",
    "AEX1M": "5",
    "AEX3M": "14",
    "AEX6M": "27",
    "AEX12M": "49",
    "AUTO1M": "24",
    "AUTO3M": "66",
    "AUTO6M": "125",
    "AUTO12M": "231",
}


def _apply(main: Any, defaults: dict[str, dict[str, object]]) -> None:
    now = main.db.now_iso()
    with main.db.conn() as con:
        row = con.execute(
            "SELECT value FROM app_settings WHERE key=?",
            (_MIGRATION_KEY,),
        ).fetchone()
        if row and str(row[0]).strip() == "1":
            return

        changed = 0
        for code, price in _APPROVED_PRICES.items():
            plan = defaults.get(code) or {}
            title_fa = str(plan.get("fa") or code)
            title_en = str(plan.get("en") or code)

            cur = con.execute(
                """UPDATE subscription_plans
                   SET title_fa=?, title_en=?, usdt_price=?, price_usdt=?, updated_at=?
                   WHERE code=?""",
                (title_fa, title_en, price, price, now, code),
            )
            changed += int(cur.rowcount or 0)

            con.execute(
                """UPDATE plans
                   SET name=?, price_usdt=?, updated_at=?
                   WHERE code=?""",
                (title_en, price, now, code),
            )

        con.execute(
            """INSERT INTO app_settings(key,value,updated_at) VALUES(?,?,?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
            (_MIGRATION_KEY, "1", now),
        )

    log.info(
        "[NEXUS][PRICING][19USD_MIGRATION] applied=true rows=%s vip=19/52/98/182 autotrade=5/14/27/49 bundle=24/66/125/231",
        changed,
    )


def install(main: Any) -> None:
    original = main.db.ensure_default_plans
    if getattr(original, "_nexus_19usd_pricing", False):
        return

    def wrapped(defaults: dict[str, dict[str, object]]) -> None:
        original(defaults)
        _apply(main, defaults)

    wrapped._nexus_19usd_pricing = True  # type: ignore[attr-defined]
    wrapped._nexus_19usd_pricing_original = original  # type: ignore[attr-defined]
    main.db.ensure_default_plans = wrapped
    log.info("[NEXUS][PRICING][19USD_RUNTIME][INSTALLED]")
