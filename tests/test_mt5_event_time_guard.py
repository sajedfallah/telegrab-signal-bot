from datetime import datetime, timezone


def test_mt5_event_time_uses_epoch_milliseconds():
    from app.autotrade.event_time_guard import mt5_event_datetime

    value = 1788402052000
    dt = mt5_event_datetime({"event_time_ms": value})
    assert dt.tzinfo is not None
    assert dt == datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)


def test_mt5_event_time_uses_iso_fallback():
    from app.autotrade.event_time_guard import mt5_event_datetime

    dt = mt5_event_datetime({"event_time_ms": 0, "event_time": "2026-09-03T03:30:00Z"})
    assert dt == datetime(2026, 9, 3, 3, 30, tzinfo=timezone.utc)


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
