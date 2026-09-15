from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

from app import db
from app.autotrade.market_quote_runtime import _fresh_market_feed_quote
from app.market_candles import MarketFeedRequest, init_market_candle_schema


ACCOUNT = "80150619"
ROOT = Path(__file__).resolve().parents[1]


def _insert_quote(*, bid: float = 4283.5, ask: float = 4283.7, age_seconds: float = 0.0) -> None:
    init_market_candle_schema()
    now = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    with db.conn() as con:
        con.execute(
            """INSERT INTO mt5_market_quotes
               (account_number,symbol,broker_symbol,bid,ask,digits,quote_time_ms,captured_at)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(account_number,symbol) DO UPDATE SET
                 broker_symbol=excluded.broker_symbol,bid=excluded.bid,ask=excluded.ask,
                 digits=excluded.digits,quote_time_ms=excluded.quote_time_ms,captured_at=excluded.captured_at""",
            (
                ACCOUNT,
                "XAUUSD",
                "XAUUSD.ec",
                bid,
                ask,
                2,
                int(now.timestamp() * 1000),
                now.isoformat(),
            ),
        )


def test_market_feed_request_accepts_real_bid_ask_tick():
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    req = MarketFeedRequest.model_validate(
        {
            "account_number": ACCOUNT,
            "quotes": [
                {
                    "symbol": "XAUUSD",
                    "broker_symbol": "XAUUSD.ec",
                    "bid": 4283.5,
                    "ask": 4283.7,
                    "digits": 2,
                    "time_msc": now_ms,
                }
            ],
            "series": [
                {
                    "symbol": "XAUUSD",
                    "broker_symbol": "XAUUSD.ec",
                    "timeframe": "M5",
                    "digits": 2,
                    "candles": [
                        {
                            "time": max(1, now_ms // 1000 - 300),
                            "open": 4283.0,
                            "high": 4284.0,
                            "low": 4282.0,
                            "close": 4283.5,
                            "tick_volume": 10,
                        }
                    ],
                }
            ],
        }
    )
    assert req.quotes[0].bid == 4283.5
    assert req.quotes[0].ask == 4283.7
    assert req.quotes[0].broker_symbol == "XAUUSD.ec"


def test_fresh_tick_is_returned_without_candle_price_inference(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "v32-fresh.db")
    _insert_quote()
    quote = _fresh_market_feed_quote(ACCOUNT, "XAUUSD")
    assert quote is not None
    assert quote["bid"] == 4283.5
    assert quote["ask"] == 4283.7
    assert quote["broker_symbol"] == "XAUUSD.ec"
    assert quote["source"] == "MT5_MARKET_FEED_TICK"
    assert quote["fresh"] is True


def test_stale_tick_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "v32-stale.db")
    _insert_quote(age_seconds=30)
    assert _fresh_market_feed_quote(ACCOUNT, "XAUUSD") is None


def test_market_feed_source_uses_symbol_info_tick_and_never_candle_close_as_quote():
    source = (ROOT / "mt5/NEXUS_MarketFeed/NEXUS_MarketFeed.mq5").read_text(encoding="utf-8-sig")
    assert "SymbolInfoTick(broker_symbol,tick)" in source
    assert "tick.bid" in source
    assert "tick.ask" in source
    assert "tick.time_msc" in source
    assert '"NEXUS-MARKET-FEED-1.1"' in source


def test_v32_runtime_precedes_v31_publish_guard_and_patches_same_market_quote_contract():
    combined = (ROOT / "app/combined_api.py").read_text(encoding="utf-8-sig")
    runtime = (ROOT / "app/autotrade/market_quote_runtime.py").read_text(encoding="utf-8-sig")
    assert "install_market_quote_runtime(app)" in combined
    assert combined.index("install_market_quote_runtime(app)") < combined.index("install_web_admin_market_entry_guard(app)")
    assert "mini.market_quote = market_quote" in runtime
    assert "MT5_MARKET_FEED_TICK" in runtime
    assert "current_price" not in runtime
    assert "FROM mt5_market_quotes" in runtime
    assert "mt5_market_candles" not in runtime
