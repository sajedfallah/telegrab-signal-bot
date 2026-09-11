from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape
from types import SimpleNamespace

import pytest


def _signal(monkeypatch, tmp_path, *, lot_size=0.02):
    from app import db

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "lifecycle_truth.db")
    db.init_db()
    uid = 400112107
    now = datetime.now(timezone.utc).isoformat()
    with db.conn() as con:
        con.execute(
            "INSERT INTO users(telegram_id,created_at,updated_at) VALUES(?,?,?)",
            (uid, now, now),
        )
    row = db.create_signal(
        market_type="GOLD",
        symbol="XAUUSD",
        direction="SELL",
        entry_price=4387.0,
        stop_loss=4410.0,
        targets=[4364.0, 4352.5, 4341.0, 4318.0],
        risk_percent=0.0,
        rr_ratio=None,
        destination="VIP",
        chart_file_id=None,
        created_by=uid,
        publish_token="PUB-V0661",
    )
    with db.conn() as con:
        con.execute(
            "UPDATE signals SET volume_mode='FIXED',lot_size=?,vip_message_id=200,vip_last_message_id=200 WHERE id=?",
            (lot_size, int(row["id"])),
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS signal_public_codes ("
            "signal_id INTEGER PRIMARY KEY, public_no INTEGER NOT NULL UNIQUE, "
            "public_code TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL)"
        )
        con.execute(
            "INSERT INTO signal_public_codes(signal_id,public_no,public_code,created_at) VALUES(?,?,?,?)",
            (int(row["id"]), 24, "NX-24", now),
        )
    return db, uid, db.get_signal(int(row["id"]))


def _fake_main(sent):
    async def reply(_bot, _row, text):
        sent.append(text)
        return None, 201, []

    return SimpleNamespace(
        _reply_signal_update=reply,
        _copy_price=lambda value: f"{float(value):g}",
        escape=escape,
        tr=lambda _lang, fa, _en: fa,
        get_lang=lambda _uid: "fa",
    )


@pytest.mark.asyncio
async def test_broker_sl_update_replies_and_advances_persisted_lifecycle(monkeypatch, tmp_path):
    db, uid, row = _signal(monkeypatch, tmp_path)
    from app.autotrade import telegram_lifecycle_truth as truth

    sent = []
    main = _fake_main(sent)
    monkeypatch.setattr(truth, "_resolve_row", lambda _uid, _payload: db.get_signal(int(row["id"])))

    payload = {
        "event": "UPDATE",
        "event_id": "UPDATE-95296019-1",
        "ticket": "95296019",
        "signal_id": str(row["code"]),
        "stop_loss": 4372.21,
        "take_profit": 4364.0,
        "account_number": "80150619",
    }
    handled = await truth._handle_update(main, object(), {"telegram_id": uid}, payload)

    assert handled is True
    assert len(sent) == 1
    assert "NX-24" in sent[0]
    assert "NX-29" not in sent[0]
    assert "Current SL" in sent[0]
    assert "4372.21" in sent[0]
    assert "Current TP" in sent[0]

    refreshed = db.get_signal(int(row["id"]))
    assert float(refreshed["stop_loss"]) == pytest.approx(4372.21)
    updates = db.signal_updates(int(row["id"]))
    assert len(updates) == 1
    assert updates[0]["action"] == "MT5_UPDATE"
    assert int(updates[0]["vip_message_id"]) == 201


@pytest.mark.asyncio
async def test_broker_partial_uses_exact_stage_profit_not_floating_snapshot(monkeypatch, tmp_path):
    db, uid, row = _signal(monkeypatch, tmp_path, lot_size=0.02)
    from app.autotrade import telegram_lifecycle_truth as truth

    monkeypatch.setenv("NEXUS_PNL_CURRENCY", "USD")
    sent = []
    main = _fake_main(sent)
    monkeypatch.setattr(truth, "_resolve_row", lambda _uid, _payload: db.get_signal(int(row["id"])))

    payload = {
        "event": "UPDATE",
        "event_id": "PARTIAL-95296019-123456",
        "ticket": "95296019",
        "signal_id": str(row["code"]),
        "close_reason": "PARTIAL",
        "volume": 0.01,
        "profit": 12.34,
        "gross_profit": 12.80,
        "commission": -0.46,
        "swap": 0.0,
        "exit_price": 4360.0,
        "stop_loss": 4372.21,
        "take_profit": 4318.0,
        "account_number": "80150619",
    }
    handled = await truth._handle_update(main, object(), {"telegram_id": uid}, payload)

    assert handled is True
    assert len(sent) == 1
    assert "Partial Close Executed" in sent[0]
    assert "Closed Volume: <code>0.01</code>" in sent[0]
    assert "Remaining Volume: <code>0.01</code>" in sent[0]
    assert "Stage Profit: <code>$+12.34</code>" in sent[0]
    assert "SL: <code>4372.21</code>" in sent[0]
    assert "TP: <code>4318</code>" in sent[0]

    updates = db.signal_updates(int(row["id"]))
    assert len(updates) == 1
    assert updates[0]["action"] == "MT5_PARTIAL_CLOSE"
    value = json.loads(str(updates[0]["value"]))
    assert value["closed_volume"] == pytest.approx(0.01)
    assert value["remaining_volume"] == pytest.approx(0.01)
    assert value["stage_profit"] == pytest.approx(12.34)


@pytest.mark.asyncio
async def test_live_snapshot_volume_fallback_never_mislabels_floating_pnl_as_stage_profit(monkeypatch, tmp_path):
    db, uid, row = _signal(monkeypatch, tmp_path, lot_size=0.02)
    from app.autotrade import telegram_lifecycle_truth as truth

    sent = []
    main = _fake_main(sent)
    monkeypatch.setattr(truth, "_resolve_row", lambda _uid, _payload: db.get_signal(int(row["id"])))

    payload = {
        "event": "UPDATE",
        "event_id": "LIVE-VOLUME-95296019-0.01000000",
        "ticket": "95296019",
        "signal_id": str(row["code"]),
        "change_source": "LIVE_SNAPSHOT_VOLUME",
        "previous_volume": 0.02,
        "volume": 0.01,
        "profit": 99.99,
    }
    handled = await truth._handle_update(main, object(), {"telegram_id": uid}, payload)

    assert handled is True
    assert sent == []
    assert db.signal_updates(int(row["id"])) == []
