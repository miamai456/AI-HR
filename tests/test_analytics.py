from aihr.services.analytics import _rate


def test_rate_handles_empty_denominator() -> None:
    assert _rate(0, 0) == 0.0
    assert _rate(None, None) == 0.0


def test_rate_rounds_to_four_decimals() -> None:
    assert _rate(1, 3) == 0.3333
