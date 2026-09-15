from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from app import db
from app.autotrade.market_quote_runtime import _fresh_market_feed_quote
from app.market_candles import init_market_candle_schema


def main() -> int:
    parser = argparse.ArgumentParser(description="Check V32 authenticated MT5 Bid/Ask feed")
    parser.add_argument("--account", default="80150619")
    parser.add_argument("--symbol", default="XAUUSD")
    args = parser.parse_args()

    init_market_candle_schema()
    with db.conn() as con:
        row = con.execute(
            """SELECT account_number,symbol,broker_symbol,bid,ask,digits,quote_time_ms,captured_at
               FROM mt5_market_quotes WHERE account_number=? AND symbol=UPPER(?) LIMIT 1""",
            (str(args.account), str(args.symbol)),
        ).fetchone()

    if not row:
        print("MARKET_QUOTE_V32: WAITING_FOR_MT5_TICK")
        return 2

    item = dict(row)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    item["quote_age_seconds"] = round((now_ms - int(item["quote_time_ms"])) / 1000.0, 3)
    fresh = _fresh_market_feed_quote(str(args.account), str(args.symbol))
    print("MARKET_QUOTE_ROW:", json.dumps(item, ensure_ascii=False, default=str))
    if not fresh:
        print("MARKET_QUOTE_V32: STALE_OR_INVALID")
        return 3
    print("MARKET_QUOTE_FRESH:", json.dumps(fresh, ensure_ascii=False, default=str))
    print("MARKET_QUOTE_V32: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
