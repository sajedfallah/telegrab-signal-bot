from __future__ import annotations

import argparse
import asyncio
import json

from app import db
from app.autotrade.broker_chart_fallback import ensure_broker_chart_asset
from app.combined_api import app  # noqa: F401 - installs runtime wrappers
from app.autotrade import api as api_mod


_ACCEPTED = {"EXECUTED", "PENDING", "ACTIVATED"}


def _accepted_receipt(signal_id: int) -> bool:
    with db.conn() as con:
        row = con.execute(
            """SELECT status FROM autotrade_signal_receipts
               WHERE signal_id=? AND platform='MT5'
               ORDER BY COALESCE(executed_at,first_seen_at) DESC LIMIT 1""",
            (int(signal_id),),
        ).fetchone()
    return bool(row and str(row["status"] or "").strip().upper() in _ACCEPTED)


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair one published NEXUS fallback card with fresh MT5 MarketFeed candles.")
    parser.add_argument("--code", required=True, help="Signal code, for example NX-54")
    args = parser.parse_args()

    signal = db.get_signal_by_code(str(args.code).strip())
    if not signal:
        raise SystemExit(f"signal not found: {args.code}")
    if str(signal["issuer_type"] or "").upper() != "WEB_ADMIN":
        raise SystemExit("refusing repair: signal is not WEB_ADMIN")
    if not (signal["free_message_id"] or signal["vip_message_id"]):
        raise SystemExit("refusing repair: signal has no existing Telegram publication anchor")
    if not _accepted_receipt(int(signal["id"])):
        raise SystemExit("refusing repair: broker-confirmed execution receipt is missing")

    staged = ensure_broker_chart_asset(signal)
    print("BROKER_CHART_STAGE:", json.dumps(staged, ensure_ascii=False))
    if not staged.get("ok"):
        raise SystemExit("broker chart staging failed")

    result = asyncio.run(api_mod._publish_mt5_admin_signal_async(signal, None, allow_without_chart=True))
    print("TELEGRAM_REPAIR_RESULT:", json.dumps(result, ensure_ascii=False))
    repaired = result.get("repaired_channels") or [] if isinstance(result, dict) else []
    if not repaired:
        raise SystemExit("Telegram media repair did not report any repaired channel")

    print("BROKER CHART REPAIR: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
