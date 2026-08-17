import pytest

from app.domain.models import CsvErrorCode
from app.services.value_validator import validate_row_values


def valid_values(**overrides: str) -> dict[str, str]:
    values = {
        "date": "2026-01-15",
        "product": "Desk Lamp",
        "category": "Office",
        "region": "North",
        "quantity": "3",
        "unit_price": "100.5",
        "discount": "0.1",
        "customer_type": "Retail",
    }
    values.update(overrides)
    return values


def codes_for(**overrides: str) -> list[CsvErrorCode]:
    return [
        error.code for error in validate_row_values(valid_values(**overrides), 12)
    ]


@pytest.mark.parametrize("value", ["2026/01/15", "15-01-2026", "2026-13-01", ""])
def test_rejects_non_iso_or_invalid_dates(value: str) -> None:
    errors = validate_row_values(valid_values(date=value), 12)

    assert errors[0].code is CsvErrorCode.INVALID_DATE
    assert errors[0].field == "date"
    assert errors[0].row == 12


def test_accepts_strict_iso_date() -> None:
    assert CsvErrorCode.INVALID_DATE not in codes_for(date="2026-01-15")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("-1", CsvErrorCode.NEGATIVE_QUANTITY),
        ("1.5", CsvErrorCode.INVALID_QUANTITY),
        ("abc", CsvErrorCode.INVALID_NUMBER),
        ("NaN", CsvErrorCode.INVALID_NUMBER),
        ("Infinity", CsvErrorCode.INVALID_NUMBER),
        ("1e2", CsvErrorCode.INVALID_NUMBER),
        ("1000000001", CsvErrorCode.INVALID_QUANTITY),
    ],
)
def test_quantity_validation(value: str, expected: CsvErrorCode) -> None:
    assert expected in codes_for(quantity=value)


@pytest.mark.parametrize("value", ["0", "1", "50", "1000000000"])
def test_accepts_quantity_integer_boundaries(value: str) -> None:
    assert codes_for(quantity=value) == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("-1", CsvErrorCode.NEGATIVE_UNIT_PRICE),
        ("abc", CsvErrorCode.INVALID_NUMBER),
        ("NaN", CsvErrorCode.INVALID_NUMBER),
        ("Infinity", CsvErrorCode.INVALID_NUMBER),
        ("1e2", CsvErrorCode.INVALID_NUMBER),
        ("1000000000.01", CsvErrorCode.UNIT_PRICE_TOO_LARGE),
    ],
)
def test_unit_price_validation(value: str, expected: CsvErrorCode) -> None:
    assert expected in codes_for(unit_price=value)


@pytest.mark.parametrize("value", ["0", "100", "100.5", "9999.99", "1000000000"])
def test_accepts_unit_price_boundaries(value: str) -> None:
    assert codes_for(unit_price=value) == []


@pytest.mark.parametrize("value", ["-0.1", "1.1", "abc", "NaN", "Infinity"])
def test_rejects_invalid_discount(value: str) -> None:
    assert CsvErrorCode.INVALID_DISCOUNT in codes_for(discount=value)


@pytest.mark.parametrize("value", ["", "0", "1", "0.5"])
def test_accepts_discount_boundaries_and_blank(value: str) -> None:
    assert codes_for(discount=value) == []


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("product", CsvErrorCode.EMPTY_PRODUCT),
        ("category", CsvErrorCode.EMPTY_CATEGORY),
        ("region", CsvErrorCode.EMPTY_REGION),
    ],
)
def test_rejects_empty_required_strings(field: str, expected: CsvErrorCode) -> None:
    assert expected in codes_for(**{field: "  "})


@pytest.mark.parametrize("field", ["product", "category", "region", "customer_type"])
def test_string_length_boundary(field: str) -> None:
    assert codes_for(**{field: "A" * 200}) == []
    assert CsvErrorCode.STRING_TOO_LONG in codes_for(**{field: "A" * 201})


def test_collects_multiple_errors_from_one_row() -> None:
    errors = validate_row_values(
        valid_values(quantity="-1", unit_price="abc", region=""), 9
    )

    assert {error.code for error in errors} == {
        CsvErrorCode.NEGATIVE_QUANTITY,
        CsvErrorCode.INVALID_NUMBER,
        CsvErrorCode.EMPTY_REGION,
    }
    assert all(error.row == 9 for error in errors)
