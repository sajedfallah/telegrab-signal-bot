from datetime import datetime, timezone, timedelta
from app.signal_agent.config import SignalAgentSettings, TIMEFRAMES
from app.signal_agent.market_data.models import Candle, Quote
from app.signal_agent.market_data.provider import MarketDataProvider
from app.signal_agent.market_data.runtime import MarketDataRuntime
from app.signal_agent.market_data.store import MarketDataStore
from app.signal_agent.market_data.timeframes import aggregate

class Fake(MarketDataProvider):
    def __init__(self,stale=False): self.stale=stale
    def quote(self,s): return Quote(s,2000,2000.2,datetime.now(timezone.utc)-timedelta(seconds=60 if self.stale else 0))
    def candles(self,s,t,limit=500): return [Candle(s,t,datetime(2026,1,1,tzinfo=timezone.utc),1,2,.5,1.5,10)]

def test_all_required_timeframes_and_restart_recovery(tmp_path):
    p=str(tmp_path/"a.db"); cfg=SignalAgentSettings(True,("XAUUSD",),30,"MT5"); store=MarketDataStore(p); out=MarketDataRuntime(Fake(),store,cfg).poll_once(); assert set(out["XAUUSD"]["candles"])==set(TIMEFRAMES); store2=MarketDataStore(p); assert store2._con().execute("select count(*) from signal_agent_candles").fetchone()[0]==5

def test_stale_quote_is_rejected(tmp_path):
    cfg=SignalAgentSettings(True,("XAUUSD",),30,"MT5"); out=MarketDataRuntime(Fake(True),MarketDataStore(str(tmp_path/"b.db")),cfg).poll_once(); assert out["XAUUSD"]["status"]=="ERROR"; assert "stale" in out["XAUUSD"]["error"]

def test_deterministic_m15_aggregation():
    z=datetime(2026,1,1,tzinfo=timezone.utc); src=[Candle("XAUUSD","M5",z+timedelta(minutes=i*5),1+i,3+i,.5+i,2+i,10) for i in range(3)]; x=aggregate("XAUUSD","M15",src)[0]; assert (x.open,x.high,x.low,x.close,x.volume)==(1,5,.5,4,30)

def test_release_a_has_no_signal_publication_imports():
    import pathlib
    root=pathlib.Path("app/signal_agent"); text="\n".join(p.read_text() for p in root.rglob("*.py")); assert "telegram" not in text.lower(); assert "issue_mt5_admin_signal" not in text
