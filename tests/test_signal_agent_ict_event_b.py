from datetime import datetime,timedelta,timezone
from app.signal_agent.market_data.models import Candle
from app.signal_agent.ict.engine import ICTEventEngine
from app.signal_agent.ict.replay import ReplayRunner
from app.signal_agent.ict.store import ICTEventStore
from app.signal_agent.ict import detectors as d
from app.signal_agent.ict.models import EventStatus
from app.signal_agent.ict.sessions import session_events
SEC={"M5":300,"M15":900,"H1":3600,"H4":14400,"D1":86400}

def mk(vals,tf="M5"):
    z=datetime(2026,1,1,tzinfo=timezone.utc);step=SEC[tf]
    return [Candle("XAUUSD",tf,z+timedelta(seconds=step*i),*v,10) for i,v in enumerate(vals)]
def fixture(tf="M5"):
    return mk([(10,11,9,10),(10,12,9.5,11),(11,11.5,8,9),(9,9.5,8.5,9),(9,9.2,8.8,9),(9,14,8.9,13.5),(13.5,14,12,12.5),(12.5,12.7,11.5,12),(12,15,11.8,14.5),(14.5,14.8,13,13.5),(13.5,13.8,12.5,13),(13,13.2,12.8,13)],tf)

def test_determinism_persistence_replay_and_health(tmp_path):
    cs=fixture();e=ICTEventEngine();asof=cs[-1].open_time+timedelta(seconds=SEC["M5"])
    direct=e.detect(cs,as_of=asof);replay=ReplayRunner(e).run(cs)
    assert {x.event_key for x in direct}=={x.event_key for x in replay}
    s=ICTEventStore(str(tmp_path/"ict.db"));s.save(direct);before=s.keys();s.save(direct);assert s.keys()==before
    s.health("OK",len(direct));assert s.runtime()["event_count"]==len(direct)

def test_core_detectors_and_sweep():
    # Confirm a swing high at index 2, then penetrate it and close back below:
    # this satisfies the existing BUY_SIDE sweep rule without weakening semantics.
    cs=mk([(10,10.5,9.5,10),(10,11,9.8,10.5),(10.5,12,10,11),(11,11.5,10.2,10.8),(10.8,11.2,10,10.5),(10.5,12.5,10.3,11.5),(11.5,11.8,10.8,11)])
    sw=d.swings(cs);liq=d.liquidity(cs,sw);sweeps=d.sweeps(cs,liq)
    assert any(x.event_type=="SWING_HIGH" for x in sw)
    assert any(x.direction=="BUY_SIDE" for x in liq)
    assert any(x.event_type=="LIQUIDITY_SWEEP" and x.direction=="BEARISH" for x in sweeps)
    assert d.displacement(fixture()) and d.premium_discount(cs)

def test_fvg_lifecycle():
    active=mk([(10,11,9,10),(11,13,10.5,12.5),(13,14,12,13.5)])
    assert d.fvgs(active)[0].status==EventStatus.ACTIVE
    mitigated=active+[Candle("XAUUSD","M5",active[-1].open_time+timedelta(minutes=5),11.5,12.5,10.8,12,10)]
    assert d.fvgs(mitigated)[0].status==EventStatus.MITIGATED
    invalid=active+[Candle("XAUUSD","M5",active[-1].open_time+timedelta(minutes=5),10.5,11,9,9.5,10)]
    assert d.fvgs(invalid)[0].status==EventStatus.INVALIDATED

def test_ob_invalidation_and_breaker():
    cs=mk([(10,10.5,9.5,10.2),(10.2,10.4,9.8,10),(10,10.2,9.7,9.8),(9.8,13,9.7,12.8),(12.8,13,9,9.2)])
    disp=d.displacement(cs,factor=1.4);obs=d.order_blocks(cs,disp)
    assert obs and any(x.status==EventStatus.INVALIDATED for x in obs)
    assert d.breakers(cs,obs)

def test_mss_and_choch_dedicated():
    # wing=1: high swing at 1, low swing at 3. Candle 5 breaks high bullish;
    # candle 6 then breaks the confirmed low bearish -> opposite MSS => CHOCH.
    cs=mk([(10,10.5,9.5,10),(10,12,10,11),(11,11.5,9.5,10),(10,10.5,8,9),(9,11,8.5,10),(10,13,9.5,12.5),(12.5,12.7,7.5,7.8),(7.8,8.5,7.6,8)])
    sw=d.swings(cs,wing=1);ev=d.structure_changes(cs,sw)
    mss=[x for x in ev if x.event_type=="MSS"]
    assert any(x.direction=="BULLISH" for x in mss)
    assert any(x.direction=="BEARISH" for x in mss)
    assert any(x.event_type=="CHOCH" and x.direction=="BEARISH" for x in ev)

def test_daily_quadrant_tie_newest_wins():
    cs=fixture("D1")[-10:];a=cs[-2];b=cs[-1]
    cs[-2]=Candle("XAUUSD","D1",a.open_time,10,15,9,11,10);cs[-1]=Candle("XAUUSD","D1",b.open_time,10,15,9,11,10)
    q=d.daily_quadrant(cs)[0];assert q.source_time==cs[-1].open_time;assert set(q.metadata["levels"])=={"25","50","75"}

def test_closed_candle_safety():
    cs=fixture();forming=cs[-1];asof=forming.open_time+timedelta(seconds=1)
    closed=ICTEventEngine().detect(cs,closed_only=True,as_of=asof)
    assert all(x.source_time<forming.open_time for x in closed)
    assert len(ICTEventEngine().detect(cs,closed_only=False))>=len(closed)

def test_all_timeframes_and_sessions():
    e=ICTEventEngine()
    for tf in SEC:
        cs=fixture(tf);asof=cs[-1].open_time+timedelta(seconds=SEC[tf]);assert e.detect(cs,as_of=asof)
    ev=session_events("XAUUSD",datetime(2026,7,1,8,tzinfo=timezone.utc));assert all("timezone" in x.metadata for x in ev)

def test_no_trade_signal_telegram_or_ai_authority():
    import pathlib
    text="\n".join(p.read_text() for p in pathlib.Path("app/signal_agent/ict").rglob("*.py")).lower()
    for forbidden in ("telegram","issue_mt5_admin_signal","openai","trade_decision","entry_price","stop_loss","take_profit"):assert forbidden not in text
