from decimal import Decimal

from app.presentation.formatters import (
    format_decimal,
    format_integer,
    format_percentage,
    format_ratio,
    format_signed_number,
    format_signed_percentage,
)


def test_decimal_display_formats_large_and_fractional_values() -> None:
    assert format_decimal(Decimal("1234567890.6700")) == "1,234,567,890.67"
    assert format_decimal(Decimal("12345.00")) == "12,345"
    assert format_decimal(Decimal("2857.941176470588235294117647")) == "2,857.94"
    assert format_decimal(Decimal("0.125")) == "0.13"
    assert format_decimal(Decimal("-20.50")) == "-20.50"


def test_none_and_percentage_display() -> None:
    assert format_decimal(None) == "N/A"
    assert format_percentage(None) == "N/A"
    assert format_percentage(Decimal("12.500")) == "12.50%"
    assert format_decimal(Decimal("NaN")) == "N/A"
    assert format_decimal(Decimal("Infinity")) == "N/A"
    assert format_integer(1234567) == "1,234,567"


def test_ratio_and_signed_business_formats() -> None:
    assert format_ratio(Decimal("0.30436346867284")) == "30.44%"
    assert format_signed_percentage(Decimal("0.952380952380")) == "+0.95%"
    assert format_signed_percentage(Decimal("-6.827")) == "-6.83%"
    assert format_signed_percentage(Decimal("0")) == "0.00%"
    assert format_signed_number(Decimal("20610")) == "+20,610"
    assert format_signed_number(Decimal("-7620")) == "-7,620"
    assert format_signed_number(Decimal("0")) == "0"
    assert format_signed_number(None) == "N/A"
