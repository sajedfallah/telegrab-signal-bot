from pathlib import Path

def fresh(monkeypatch, tmp_path):
    from app import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "db.sqlite")
    db.init_db()
    db.start_new_cycle("CYCLE-TEST-001")
    return db

def test_cycle_is_assigned_to_new_signals(monkeypatch, tmp_path):
    db=fresh(monkeypatch,tmp_path)
    row=db.create_signal(market_type="CRYPTO",symbol="BTCUSDT",direction="LONG",entry_price=100,stop_loss=95,targets=[110],risk_percent=1,rr_ratio=2,destination="VIP",chart_file_id=None,created_by=1,publish_token="C1")
    assert row["cycle_id"] == "CYCLE-TEST-001"

def test_reconciled_execution_stores_broker_costs(monkeypatch, tmp_path):
    db=fresh(monkeypatch,tmp_path)
    db.upsert_user(100,"u","U")
    row=db.create_signal(market_type="CRYPTO",symbol="BTCUSDT",direction="LONG",entry_price=100,stop_loss=95,targets=[110],risk_percent=1,rr_ratio=2,destination="VIP",chart_file_id=None,created_by=100,publish_token="SIG-COST")
    with db.conn() as con: con.execute("UPDATE signals SET status='ACTIVE' WHERE id=?",(row["id"],))
    item={"event":"CLOSE","ticket":"T1","event_id":"R1","signal_id":"SIG-COST","symbol":"BTCUSDT","direction":"LONG","volume":1,"entry_price":100,"stop_loss":95,"take_profit":110,"exit_price":108,"profit":7.5,"gross_profit":9,"commission":-1,"swap":-.5,"risk_cash":5,"position_id":"P1","deal_id":"D1","event_time_ms":1750000000000,"destination":"BOTH"}
    out=db.reconcile_mt5_history(100,[item])
    assert out["created"] == 1
    ex=db.autotrade_trade_executions(100,limit=10)[0]
    assert ex["commission"] == -1
    assert ex["swap"] == -.5
    assert ex["gross_profit"] == 9

def test_unified_report_uses_execution_truth(monkeypatch,tmp_path):
    db=fresh(monkeypatch,tmp_path)
    db.upsert_user(101,"u","U")
    row=db.create_signal(market_type="CRYPTO",symbol="BTCUSDT",direction="LONG",entry_price=100,stop_loss=95,targets=[110],risk_percent=1,rr_ratio=2,destination="VIP",chart_file_id=None,created_by=101,publish_token="SIG-RPT")
    with db.conn() as con: con.execute("UPDATE signals SET status='ACTIVE' WHERE id=?",(row["id"],))
    db.enqueue_autotrade_trade_event(101,"OPEN",{"event":"OPEN","event_id":"O1","signal_id":"SIG-RPT","symbol":"BTCUSDT","direction":"LONG","volume":1,"entry_price":100,"stop_loss":95,"take_profit":110,"position_id":"P1","deal_id":"D1","risk_cash":5},"D1")
    db.enqueue_autotrade_trade_event(101,"CLOSE",{"event":"CLOSE","event_id":"C1","signal_id":"SIG-RPT","symbol":"BTCUSDT","direction":"LONG","volume":1,"entry_price":100,"stop_loss":95,"take_profit":110,"exit_price":108,"profit":7.5,"gross_profit":9,"commission":-1,"swap":-.5,"position_id":"P1","deal_id":"D2","risk_cash":5},"D2")
    report=db.unified_cycle_report(101)
    assert report["closed"] == 1
    assert report["net_pnl"] == 7.5
    assert report["avg_realized_r"] == 1.5
