from datetime import datetime,timedelta,timezone
from app.signal_agent.market_data.models import Candle
from app.signal_agent.ict.engine import ICTEventEngine
from app.signal_agent.ict.replay import ReplayRunner
from app.signal_agent.ict.store import ICTEventStore
from app.signal_agent.ict.detectors import daily_quadrant
from app.signal_agent.ict.sessions import session_events

def candles(tf="M5",n=12):
    z=datetime(2026,1,1,tzinfo=timezone.utc); out=[]
    vals=[(10,11,9,10.5),(10.5,12,10,11.5),(11.5,11.7,9.5,10),(10,10.2,8,8.5),(8.5,9,8.2,8.8),(8.8,13,8.7,12.8),(12.8,13.2,12,12.2),(12.2,12.5,11.8,12),(12,14,11.9,13.8),(13.8,14,13,13.2),(13.2,13.5,12.8,13),(13,13.3,12.7,13.1)]
    for i,(o,h,l,c) in enumerate(vals[:n]):out.append(Candle("XAUUSD",tf,z+timedelta(minutes=5*i),o,h,l,c,10))
    return out

def test_determinism_dedup_persistence_and_replay(tmp_path):
    cs=candles(); e=ICTEventEngine(); direct=e.detect(cs); replay=ReplayRunner(e).run(cs)
    assert {x.event_key for x in direct}.issubset({x.event_key for x in replay})
    assert len({x.event_key for x in direct})==len(direct)
    s=ICTEventStore(str(tmp_path/"ict.db")); s.save(direct); before=s.keys(); s.save(direct); assert s.keys()==before

def test_core_event_families_exist():
    types={x.event_type for x in ICTEventEngine().detect(candles())}
    assert {"SWING_HIGH","SWING_LOW","LIQUIDITY_POOL","DISPLACEMENT","FVG","MSS","PREMIUM_DISCOUNT"}.issubset(types)

def test_daily_quadrant_last_10_longest_wick_and_levels():
    cs=candles("D1"); cs[-1]=Candle("XAUUSD","D1",cs[-1].open_time,10,20,9,11,10)
    q=daily_quadrant(cs)[0]; assert q.source_time==cs[-1].open_time
    assert set(q.metadata["levels"])=={"25","50","75"}

def test_timezone_session_context():
    ts=datetime(2026,7,1,8,tzinfo=timezone.utc); ev=session_events("XAUUSD",ts)
    assert all("timezone" in x.metadata for x in ev)

def test_no_trade_signal_telegram_or_ai_authority():
    import pathlib
    text="\n".join(p.read_text() for p in pathlib.Path("app/signal_agent/ict").rglob("*.py")).lower()
    for forbidden in ("telegram","issue_mt5_admin_signal","openai","trade_decision","entry_price","stop_loss","take_profit"): assert forbidden not in text
