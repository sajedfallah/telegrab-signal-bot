from datetime import datetime, timezone, timedelta
import time
from app.signal_agent.config import SignalAgentSettings, TIMEFRAMES
from app.signal_agent.market_data.models import Candle, Quote
from app.signal_agent.market_data.provider import MarketDataProvider
from app.signal_agent.market_data.mt5_provider import MT5MarketDataProvider
from app.signal_agent.market_data.runtime import MarketDataRuntime
from app.signal_agent.market_data.store import MarketDataStore
from app.signal_agent.market_data.timeframes import aggregate, bucket_start

class Fake(MarketDataProvider):
    def __init__(self,stale=False,empty=False): self.stale=stale; self.empty=empty; self.calls=0
    def quote(self,s): self.calls+=1; return Quote(s,2000,2000.2,datetime.now(timezone.utc)-timedelta(seconds=60 if self.stale else 0))
    def candles(self,s,t,limit=500):
        if self.empty:return []
        return [Candle(s,t,datetime(2026,1,1,tzinfo=timezone.utc),1,2,.5,1.5,10)]

def cfg(enabled=True): return SignalAgentSettings(enabled,("XAUUSD",),30,"MT5",.05)

def test_all_required_timeframes_and_restart_hydration(tmp_path):
    p=str(tmp_path/"a.db"); r=MarketDataRuntime(Fake(),MarketDataStore(p),cfg()); out=r.poll_once(); assert set(out["XAUUSD"]["candles"])==set(TIMEFRAMES)
    restored=MarketDataRuntime(Fake(),MarketDataStore(p),cfg()); assert restored.state["XAUUSD"]["quote"]["bid"]==2000; assert set(restored.state["XAUUSD"]["candles"])==set(TIMEFRAMES)

def test_stale_and_missing_are_rejected(tmp_path):
    for n,provider in enumerate((Fake(stale=True),Fake(empty=True))):
        out=MarketDataRuntime(provider,MarketDataStore(str(tmp_path/f"{n}.db")),cfg()).poll_once(); assert out["XAUUSD"]["status"]=="ERROR"

def test_timeframe_boundaries_and_aggregation():
    z=datetime(2026,1,1,3,59,59,tzinfo=timezone.utc)
    expected={"M5":(3,55),"M15":(3,45),"H1":(3,0),"H4":(0,0),"D1":(0,0)}
    for tf,(h,m) in expected.items():
        b=bucket_start(z,tf); assert (b.hour,b.minute,b.second)==(h,m,0)
    src=[Candle("XAUUSD","M5",datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(minutes=i*5),1+i,3+i,.5+i,2+i,10) for i in range(3)]
    x=aggregate("XAUUSD","M15",src)[0]; assert (x.open,x.high,x.low,x.close,x.volume)==(1,5,.5,4,30)

def test_always_on_start_stop_and_disabled_guard(tmp_path):
    f=Fake(); r=MarketDataRuntime(f,MarketDataStore(str(tmp_path/"w.db")),cfg()); assert r.start(); time.sleep(.13); r.stop(); assert f.calls>=1; assert not r._thread.is_alive()
    off=MarketDataRuntime(Fake(),MarketDataStore(str(tmp_path/"off.db")),cfg(False)); assert off.start() is False

class Tick:
    bid=1.1; ask=1.2; time=1767225600
class MT5Fixture:
    TIMEFRAME_M5=5; TIMEFRAME_M15=15; TIMEFRAME_H1=60; TIMEFRAME_H4=240; TIMEFRAME_D1=1440
    def __init__(self,empty=False): self.empty=empty; self.calls=[]
    def symbol_info_tick(self,s): self.calls.append(("tick",s)); return Tick()
    def copy_rates_from_pos(self,s,tf,pos,limit):
        self.calls.append(("rates",s,tf,pos,limit))
        if self.empty:return []
        return [{"time":1767225600,"open":1.0,"high":2.0,"low":.5,"close":1.5,"tick_volume":42}]
def test_mt5_provider_contract_and_empty_detection():
    m=MT5Fixture(); p=MT5MarketDataProvider(m); q=p.quote("XAUUSD"); assert (q.bid,q.ask)==(1.1,1.2)
    for tf in TIMEFRAMES: assert p.candles("XAUUSD",tf)[0].timeframe==tf
    assert len([x for x in m.calls if x[0]=="rates"])==5
    try: MT5MarketDataProvider(MT5Fixture(True)).candles("XAUUSD","M5"); assert False
    except RuntimeError as e: assert "missing MT5 candles" in str(e)

def test_release_a_has_no_signal_publication_imports():
    import pathlib
    root=pathlib.Path("app/signal_agent"); text="\n".join(p.read_text() for p in root.rglob("*.py")); assert "telegram" not in text.lower(); assert "issue_mt5_admin_signal" not in text
