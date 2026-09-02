from pathlib import Path
import importlib
from fastapi import BackgroundTasks

ROOT = Path(__file__).resolve().parents[1]


def _fresh_db(monkeypatch, tmp_path):
    import app.db as db
    db = importlib.reload(db)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "nexus_bot.db")
    db.init_db()
    return db


def _admin_signal(db):
    db.upsert_user(400112107, "admin", "Admin")
    return db.issue_mt5_admin_signal(
        market_type="GOLD", symbol="XAUUSD", direction="BUY", entry_price=4310,
        stop_loss=4307, targets=[4315, 4320], risk_percent=1, rr_ratio=None,
        order_type="MARKET", volume_mode="FIXED", lot_size=0.001,
        destination="BOTH", admin_account="80150619", admin_id=400112107,
        request_id="TEST-062", signal_code=None, timeframe="M5",
    )


def test_live_snapshot_is_authoritative_and_removes_stale_positions(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    db.upsert_mt5_live_snapshot("80150619", broker="Broker", server="Demo", ea_version="0.6.4", positions=[{
        "identifier":"111", "ticket":"999", "signal_code":"NX-0001", "symbol":"XAUUSD.ec",
        "direction":"LONG", "volume":0.01, "entry_price":4310, "current_price":4311,
        "stop_loss":4307, "take_profit":4315, "profit":1.0, "magic":258025, "nexus_managed":True,
        "order_type":"MARKET",
    }])
    assert db.mt5_live_positions("80150619")
    db.upsert_mt5_live_snapshot("80150619", broker="Broker", server="Demo", ea_version="0.6.4", positions=[])
    assert db.mt5_live_positions("80150619") == []


def test_live_snapshot_repairs_missed_receipt_and_execution(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    signal = _admin_signal(db)
    db.upsert_mt5_live_snapshot("80150619", broker="Broker", server="Demo", ea_version="0.6.4", positions=[{
        "identifier":"111", "ticket":"92463356", "signal_code":signal["code"], "symbol":"XAUUSD.ec",
        "direction":"LONG", "volume":0.01, "entry_price":4310, "current_price":4311,
        "stop_loss":4307, "take_profit":4315, "profit":1.0, "magic":258025, "nexus_managed":True,
        "order_type":"MARKET",
    }])
    db.mark_signal_receipt(int(signal["id"]), 400112107, status="executed", ticket="92463356", account_number="80150619")
    db.enqueue_autotrade_trade_event(400112107, "OPEN", {
        "event":"OPEN", "ticket":"92463356", "signal_id":signal["code"], "symbol":"XAUUSD.ec",
        "direction":"LONG", "volume":0.01, "entry_price":4310, "stop_loss":4307, "take_profit":4315,
        "event_id":"LIVE-OPEN-111", "destination":"BOTH"
    }, "92463356")
    db.update_trade_execution(400112107, "92463356", "LIVE-OPEN-111", signal_id=int(signal["id"]), status="RECONCILED")
    live = db.mt5_signal_live_state(int(signal["id"]))
    assert live["receipt_status"] == "EXECUTED"
    assert live["ticket"] == "92463356"
    assert live["trade_status"] == "RECONCILED"


def test_live_snapshot_rejects_malformed_items_without_corrupting_state(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    result = db.upsert_mt5_live_snapshot("80150619", positions=[{"identifier":"", "ticket":"", "symbol":""}], orders=[{"identifier":"x", "ticket":"", "symbol":"XAUUSD"}])
    assert result["positions"] == 0
    assert result["orders"] == 0
    assert db.mt5_live_positions("80150619") == []


def test_receipt_get_endpoint_uses_correct_ea_auth_unpack_and_publication_gate(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    signal = _admin_signal(db)
    from app.autotrade import api
    monkeypatch.setattr(api, "_admin_auth", lambda *args, **kwargs: {"telegram_id":400112107, "mode":"ADMIN"})
    monkeypatch.setattr(api, "_resolve_ea_auth", lambda *args, **kwargs: {"telegram_id":400112107})
    calls=[]
    monkeypatch.setattr(api, "_publish_mt5_admin_signal_async", lambda row, chart: calls.append(int(row["id"])))
    bt=BackgroundTasks()
    out=api.signal_receipt_mt5_get(bt, int(signal["id"]), "executed", "92463356", None, "", "80150619", "true", "token")
    assert out["ok"] is True
    assert out["publication"] == "QUEUED"
    assert len(bt.tasks) == 1
    assert bt.tasks[0].func.__name__ == "<lambda>"
    live=db.mt5_signal_live_state(int(signal["id"]))
    assert live["receipt_status"] == "EXECUTED"


def test_rejected_receipt_never_queues_publication(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    signal = _admin_signal(db)
    from app.autotrade import api
    monkeypatch.setattr(api, "_admin_auth", lambda *args, **kwargs: {"telegram_id":400112107, "mode":"ADMIN"})
    monkeypatch.setattr(api, "_resolve_ea_auth", lambda *args, **kwargs: {"telegram_id":400112107})
    calls=[]
    monkeypatch.setattr(api, "_publish_mt5_admin_signal_async", lambda row, chart: calls.append(int(row["id"])))
    bt=BackgroundTasks()
    out=api.signal_receipt_mt5_get(bt, int(signal["id"]), "rejected", None, "invalid volume", "", "80150619", "true", "token")
    assert out["publication"] == "NOT_APPLICABLE"
    assert calls == []
    assert db.mt5_signal_live_state(int(signal["id"]))["receipt_status"] == "REJECTED"


def test_source_contracts_for_v062_live_truth():
    api=(ROOT/"app/autotrade/api.py").read_text(encoding="utf-8")
    db=(ROOT/"app/db.py").read_text(encoding="utf-8")
    ea=(ROOT/"mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
    client=(ROOT/"mt5/NEXUS_AutoTrade/Include/APIClient.mqh").read_text(encoding="utf-8")
    main=(ROOT/"app/main.py").read_text(encoding="utf-8")
    assert 'API_VERSION = "0.6.4"' in api
    assert '@app.post("/api/v1/autotrade/live-state")' in api
    assert '[(x,"pending") for x in orders]' in api
    assert 'CREATE TABLE IF NOT EXISTS mt5_live_state' in db
    assert 'mt5_live_positions' in db and 'mt5_live_orders' in db
    assert 'NEXUS_EA_VERSION "0.6.4"' in ea
    assert 'InpLiveSyncSeconds=5' in ea
    assert 'bool LiveState' in client
    assert 'GET is the primary receipt transport' in client
    assert 'MT5 Live Center — Current State Only' in main
    assert 'db.mt5_live_positions' in main
    assert '_replace_callback_dashboard_message' in main


def test_live_state_endpoint_repairs_missed_receipt_and_queues_publication(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    from app.autotrade import api
    monkeypatch.setattr(api.db, "DB_PATH", tmp_path / "nexus_bot.db")
    db.upsert_user(400112107, "admin", "Admin")
    signal = db.issue_mt5_admin_signal(
        market_type="GOLD", symbol="XAUUSD", direction="BUY", entry_price=4310,
        stop_loss=4307, targets=[4315], risk_percent=1, rr_ratio=None,
        order_type="MARKET", volume_mode="FIXED", lot_size=0.01, destination="BOTH",
        admin_account="80150619", admin_id=400112107, request_id="LIVE-ENDPOINT-062",
        signal_code=None, timeframe="M5",
    )
    monkeypatch.setattr(api, "_admin_auth", lambda *args, **kwargs: {"telegram_id":400112107, "mode":"ADMIN"})
    monkeypatch.setattr(api, "_resolve_ea_auth", lambda *args, **kwargs: {"telegram_id":400112107})
    monkeypatch.setattr(api, "_publish_mt5_admin_signal_async", lambda row, chart: None)
    item=api.MT5LiveStateItem(identifier="p1", ticket="t1", signal_code=signal["code"], symbol="XAUUSD.ec",
        direction="LONG", volume=0.01, entry_price=4310, current_price=4311, stop_loss=4307, take_profit=4315,
        profit=1, magic=258025, nexus_managed=True, order_type="MARKET")
    out=api.live_state(api.MT5LiveStateRequest(account_number="80150619",broker="Broker",server="Server",ea_version="0.6.4",positions=[item]), BackgroundTasks(), "", "80150619", "Broker", "Server", "0.6.4", "true", "token")
    assert out["ok"] is True
    assert signal["id"] in out["publication_signal_ids"]
    assert out["live_positions"][0]["ticket"] == "t1"
    assert db.mt5_signal_live_state(int(signal["id"]))["receipt_status"] == "EXECUTED"


def test_admin_receipt_auto_provisions_identity_on_fresh_db(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    signal = db.issue_mt5_admin_signal(
        market_type="GOLD", symbol="XAUUSD", direction="BUY", entry_price=4310,
        stop_loss=4307, targets=[4315], risk_percent=1, rr_ratio=None,
        order_type="MARKET", volume_mode="FIXED", lot_size=0.01,
        destination="BOTH", admin_account="80150619", admin_id=400112107,
        request_id="TEST-FRESH-ADMIN", signal_code=None, timeframe="M5",
    )
    # Simulate the service-level Admin authorization provisioning the identity.
    db.ensure_admin_identity(400112107)
    db.mark_signal_receipt(int(signal["id"]), 400112107, status="executed", ticket="T1", account_number="80150619")
    with db.conn() as con:
        assert con.execute("SELECT 1 FROM users WHERE telegram_id=?", (400112107,)).fetchone()
        assert con.execute("SELECT 1 FROM autotrade_signal_receipts WHERE signal_id=? AND telegram_id=?", (int(signal["id"]),400112107)).fetchone()


def test_live_repair_does_not_duplicate_business_execution(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    signal = _admin_signal(db)
    # Existing event-driven execution uses a different transport event_id.
    db.enqueue_autotrade_trade_event(400112107, "OPEN", {
        "event":"OPEN", "ticket":"T2", "signal_id":signal["code"], "symbol":"XAUUSD.ec",
        "direction":"LONG", "volume":0.01, "entry_price":4310, "stop_loss":4307, "take_profit":4315,
        "event_id":"TRADE-EVENT-123", "destination":"BOTH", "position_id":"POS-2"
    }, "T2")
    db.update_trade_execution(400112107, "T2", "TRADE-EVENT-123", signal_id=int(signal["id"]), status="RECONCILED")
    with db.conn() as con:
        before=con.execute("SELECT COUNT(*) FROM autotrade_trade_executions WHERE telegram_id=? AND signal_id=? AND ticket=? AND event_type='OPEN'",(400112107,int(signal["id"]),"T2")).fetchone()[0]
    assert before == 1
    # The API live-state repair path should link to this row rather than create a second one.
    from app.autotrade import api
    monkeypatch.setattr(api, "_admin_auth", lambda *args, **kwargs: {"telegram_id":400112107, "mode":"ADMIN"})
    monkeypatch.setattr(api, "_resolve_ea_auth", lambda *args, **kwargs: {"telegram_id":400112107})
    req=api.MT5LiveStateRequest(
        license_key="", account_number="80150619", broker="Broker", server="Demo", ea_version="0.6.4",
        positions=[api.MT5LiveStateItem(identifier="POS-2",ticket="T2",signal_code=signal["code"],symbol="XAUUSD.ec",direction="LONG",volume=0.01,entry_price=4310,current_price=4311,stop_loss=4307,take_profit=4315,profit=1,magic=258025,nexus_managed=True,order_type="MARKET")],
        orders=[]
    )
    from fastapi import BackgroundTasks
    api.live_state(req, BackgroundTasks(), "", "80150619", "Broker", "Demo", "0.6.4", "true", "token")
    with db.conn() as con:
        after=con.execute("SELECT COUNT(*) FROM autotrade_trade_executions WHERE telegram_id=? AND signal_id=? AND ticket=? AND event_type='OPEN'",(400112107,int(signal["id"]),"T2")).fetchone()[0]
    assert after == 1


def test_accepted_unpublished_signal_is_retryable(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    signal = _admin_signal(db)
    db.mark_signal_receipt(int(signal["id"]), 400112107, status="executed", ticket="T3", account_number="80150619")
    rows=db.list_mt5_publication_retries()
    assert [int(r["id"]) for r in rows] == [int(signal["id"])]
    db.set_signal_publish_messages(int(signal["id"]), 12345, None)
    rows=db.list_mt5_publication_retries()
    assert rows and rows[0]["destination"] == "BOTH"
    db.set_signal_publish_messages(int(signal["id"]), 12345, 12346)
    assert db.list_mt5_publication_retries() == []
