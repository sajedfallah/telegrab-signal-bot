from pathlib import Path

from app.autotrade.symbol_registry import infer_category

ROOT = Path(__file__).resolve().parents[1]


def test_market_categories_cover_admin_assets():
    assert infer_category("XAUUSD") == "GOLD"
    assert infer_category("XAGUSD") == "GOLD"
    assert infer_category("EURUSD") == "FOREX"
    assert infer_category("BTCUSD") == "CRYPTO"
    assert infer_category("US30") == "INDEX"
    assert infer_category("NAS100") == "INDEX"
    assert infer_category("SPX500") == "INDEX"
    assert infer_category("GER40") == "INDEX"
    assert infer_category("UK100") == "INDEX"


def test_admin_market_quote_endpoint_reads_authoritative_mt5_snapshot():
    src = (ROOT / "app" / "miniapp_admin_api.py").read_text(encoding="utf-8")
    start = src.index('@router.get("/market-quote")')
    block = src[start:src.index('@router.post("/signals"', start)]
    assert "db.mt5_market_quote" in block
    assert "age <= 15.0" in block
    assert "authoritative MT5 bid/ask quote feed is not available" not in block


def test_live_state_contract_accepts_quotes():
    src = (ROOT / "app" / "autotrade" / "api.py").read_text(encoding="utf-8")
    assert "class MT5QuoteItem(BaseModel)" in src
    assert "quotes: list[MT5QuoteItem]" in src
    assert "quotes=[i.model_dump() for i in req.quotes]" in src
    assert "quotes=quotes" in src


def test_db_persists_one_quote_per_account_and_canonical_symbol():
    src = (ROOT / "app" / "db.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS mt5_symbol_quotes" in src
    assert "PRIMARY KEY(account_number,symbol)" in src
    assert "def mt5_market_quote" in src
    assert "quote_count" in src


def test_mt5_ea_publishes_admin_symbol_quotes_with_live_state():
    ea = (ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
    client = (ROOT / "mt5" / "NEXUS_AutoTrade" / "Include" / "APIClient.mqh").read_text(encoding="utf-8")
    assert "string BuildLiveQuotesJson()" in ea
    for symbol in ("XAUUSD", "XAGUSD", "EURUSD", "GBPJPY", "BTCUSD", "US30", "NAS100", "GER40", "UK100"):
        assert f'"{symbol}"' in ea
    assert "SymbolInfoTick(broker_symbol,tick)" in ea
    assert "BuildLiveQuotesJson()" in ea
    assert '\"quotes\":[%s]' in client


def test_index_aliases_are_broker_resolvable():
    src = (ROOT / "mt5" / "NEXUS_AutoTrade" / "Include" / "SymbolMapper.mqh").read_text(encoding="utf-8")
    for token in ("US30", "DOWJONES", "NAS100", "US100", "NASDAQ", "SPX500", "GER40", "UK100"):
        assert token in src
