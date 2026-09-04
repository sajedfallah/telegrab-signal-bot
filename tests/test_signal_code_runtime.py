from app.signal_code_runtime import format_signal_code


def test_signal_code_uses_two_digit_minimum_width():
    assert format_signal_code(1) == "NX-01"
    assert format_signal_code(9) == "NX-09"
    assert format_signal_code(10) == "NX-10"
    assert format_signal_code(99) == "NX-99"
    assert format_signal_code(100) == "NX-100"
