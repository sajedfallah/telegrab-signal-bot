import os

from app.payment_display_sanitizer import repair_payment_owner_env, repair_utf8_mojibake


def test_repairs_persian_utf8_mojibake():
    original = "ساجد فلاح"
    broken = original.encode("utf-8").decode("latin1")
    assert repair_utf8_mojibake(broken) == original


def test_payment_owner_env_is_repaired(monkeypatch):
    original = "ساجد فلاح"
    broken = original.encode("utf-8").decode("latin1")
    monkeypatch.setenv("PAYMENT_OWNER", broken)
    assert repair_payment_owner_env() == original
    assert os.environ["PAYMENT_OWNER"] == original


def test_clean_ascii_is_left_unchanged():
    assert repair_utf8_mojibake("NEXUS") == "NEXUS"
