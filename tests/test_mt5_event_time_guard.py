from datetime import datetime, timedelta, timezone


def test_mt5_event_time_uses_epoch_milliseconds_for_plausible_utc_time():
    from app.autotrade.event_time_guard import mt5_event_datetime

    expected = datetime.now(timezone.utc) - timedelta(minutes=30)
    value = int(expected.timestamp() * 1000)
    dt = mt5_event_datetime({"event_time_ms": value})
    assert dt.tzinfo is not None
    assert abs((dt - expected).total_seconds()) < 0.01


def test_mt5_event_time_uses_iso_fallback():
    from app.autotrade.event_time_guard import mt5_event_datetime

    expected = datetime.now(timezone.utc) - timedelta(minutes=20)
    raw = expected.isoformat()
    dt = mt5_event_datetime({"event_time_ms": 0, "event_time": raw})
    assert abs((dt - expected).total_seconds()) < 0.01


def test_mt5_event_time_corrects_three_hour_broker_server_skew():
    from app.autotrade.event_time_guard import mt5_event_datetime

    before = datetime.now(timezone.utc)
    broker_server_time = before + timedelta(hours=3)
    dt = mt5_event_datetime({"event_time_ms": int(broker_server_time.timestamp() * 1000)})
    after = datetime.now(timezone.utc)

    # ePlanet live proof: DEAL_TIME was +03:00 relative to backend UTC. The
    # corrected lifecycle time must land back at the real near-now event time.
    assert before - timedelta(seconds=2) <= dt <= after + timedelta(seconds=2)


def test_mt5_event_time_rejects_unrecoverable_future_timestamp():
    from app.autotrade.event_time_guard import mt5_event_datetime

    before = datetime.now(timezone.utc)
    impossible = before + timedelta(hours=20)
    dt = mt5_event_datetime({"event_time_ms": int(impossible.timestamp() * 1000)})
    after = datetime.now(timezone.utc)
    assert before <= dt <= after


def test_mt5_event_time_does_not_treat_deal_ticket_as_epoch():
    from app.autotrade.event_time_guard import mt5_event_datetime

    before = datetime.now(timezone.utc)
    dt = mt5_event_datetime({"event_time_ms": 75990511})
    after = datetime.now(timezone.utc)
    assert before <= dt <= after


def test_mt5_event_time_installs_into_main_namespace():
    import app.main as main_module
    from app.autotrade.event_time_guard import install_mt5_event_datetime_helper, mt5_event_datetime

    if hasattr(main_module, "_mt5_event_datetime"):
        delattr(main_module, "_mt5_event_datetime")
    assert install_mt5_event_datetime_helper() is True
    assert main_module._mt5_event_datetime is mt5_event_datetime
