from decimal import Decimal

from app.presentation.formatters import (
    format_decimal,
    format_integer,
    format_percentage,
)


def test_decimal_display_formats_large_and_fractional_values() -> None:
    assert format_decimal(Decimal("1234567890.6700")) == "1,234,567,890.67"
    assert format_decimal(Decimal("12345.00")) == "12,345"
    assert format_decimal(Decimal("0.125")) == "0.125"
    assert format_decimal(Decimal("-20.50")) == "-20.5"


def test_none_and_percentage_display() -> None:
    assert format_decimal(None) == "N/A"
    assert format_percentage(None) == "N/A"
    assert format_percentage(Decimal("12.500")) == "12.5%"
    assert format_integer(1234567) == "1,234,567"
