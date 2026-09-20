from datetime import datetime,timedelta,timezone
from app.signal_agent.market_data.models import Candle
from app.signal_agent.ict.models import ICTEvent,EventStatus
from app.signal_agent.context.engine import ContextEngine
from app.signal_agent.context.replay import ContextReplay
from app.signal_agent.context.store import ContextStore

SEC={"M5":300,"M15":900,"H1":3600,"H4":14400,"D1":86400}
AS_OF=datetime(2026,1,10,tzinfo=timezone.utc)

def candles(tf):
    s=SEC[tf]
    return [Candle("XAUUSD",tf,AS_OF-timedelta(seconds=s*(8-i)),10+i,12+i,9+i,11+i,10) for i in range(8)]

def ev(tf,t,typ,d,ref=None,lo=None,hi=None,status=EventStatus.ACTIVE,meta=None):
    return ICTEvent("XAUUSD",tf,typ,d,t,t,lo,hi,ref,status,metadata=meta or {})

def fixture():
    c={tf:candles(tf) for tf in SEC}
    e=[
        ev("D1",c["D1"][1].open_time,"MSS","BULLISH",12),
        ev("H4",c["H4"][2].open_time,"MSS","BULLISH",12),
        ev("H1",c["H1"][2].open_time,"MSS","BULLISH",12),
        ev("M15",c["M15"][2].open_time,"MSS","BEARISH",12),
        ev("M5",c["M5"][2].open_time,"MSS","BEARISH",12),
        ev("D1",c["D1"][1].open_time,"DAILY_QUADRANT","UPPER",lo=14,hi=20,ref=17,meta={"levels":{"25":15.5,"50":17,"75":18.5}}),
        ev("H1",c["H1"][3].open_time,"LIQUIDITY_POOL","BUY_SIDE",ref=25),
        ev("H1",c["H1"][4].open_time,"LIQUIDITY_POOL","SELL_SIDE",ref=10),
        ev("M15",c["M15"][4].open_time,"LIQUIDITY_SWEEP","BULLISH",ref=10),
        ev("H1",c["H1"][3].open_time,"FVG","BULLISH",lo=15,hi=16),
    ]
    return c,e

def test_context_mtf_bias_location_quadrant_liquidity_poi_session():
    c,e=fixture();a=AS_OF
    filtered=[x for x in e if x.symbol.upper()=="XAUUSD" and x.source_time<=a]
    assert len(filtered)==len(e)
    assert all(x.source_time<=a for x in e)
    for tf in SEC:
        structural=[x for x in filtered if x.timeframe.upper()==tf and x.event_type in ("MSS","CHOCH")]
        assert structural and structural[-1].source_time<=a
        assert c[tf][-1].open_time+timedelta(seconds=SEC[tf])<=a
    s=ContextEngine().build("XAUUSD",c,e,a)
    assert s.timeframe_bias=={"D1":"BULLISH","H4":"BULLISH","H1":"BULLISH","M15":"BEARISH","M5":"BEARISH"}
    assert s.htf_bias=="BULLISH"
    assert s.structure_alignment=="HTF_ALIGNED_LTF_COUNTERTREND"
    assert set(s.timeframe_bias)==set(SEC)
    assert s.dealing_range and s.price_location in ("PREMIUM","DISCOUNT","EQUILIBRIUM")
    assert s.daily_quadrant["priority_levels"]==["50","75"]
    assert s.liquidity["nearest_buy_side"];assert s.recent_sweeps;assert s.active_pois

def test_closed_candle_no_lookahead_and_live_replay_equal():
    c,e=fixture();forming=c["M5"][-1];a=forming.open_time+timedelta(seconds=1)
    live=ContextEngine().build("XAUUSD",c,e,a);rep=ContextReplay(ContextEngine()).run("XAUUSD",c,e,a)
    assert live.context_key==rep.context_key and live.payload_json()==rep.payload_json()
    assert live.price==c["M5"][-2].close

def test_immutable_persistence_sources_restart_observability(tmp_path):
    c,e=fixture();s=ContextEngine().build("XAUUSD",c,e,AS_OF)
    db=str(tmp_path/"c.db");st=ContextStore(db);st.save(s);before=st.keys();st.save(s);assert st.keys()==before
    st2=ContextStore(db);assert st2.keys()==before;st2.health("XAUUSD","OK",1);assert st2.runtime("XAUUSD")["context_count"]==1

def test_deterministic_key_and_states():
    c,e=fixture();x=ContextEngine().build("XAUUSD",c,e,AS_OF);y=ContextEngine().build("XAUUSD",c,list(reversed(e)),AS_OF)
    assert x.context_key==y.context_key;assert x.context_state in {"TRENDING","RANGING","TRANSITION","CONFLICTED","INSUFFICIENT_DATA"}

def test_historical_replay_cutoff():
    c,e=fixture();cut=c["M5"][5].open_time+timedelta(seconds=300);future=ev("M5",c["M5"][7].open_time,"CHOCH","BEARISH")
    a=ContextEngine().build("XAUUSD",c,e,cut);b=ContextEngine().build("XAUUSD",c,e+[future],cut);assert a.context_key==b.context_key

def test_safety_boundaries():
    import pathlib
    text="\n".join(p.read_text() for p in pathlib.Path("app/signal_agent/context").rglob("*.py")).lower()
    for forbidden in ("telegram","openai","issue_mt5_admin_signal","trade_decision","entry_price","stop_loss","take_profit","setup_score"):assert forbidden not in text
