from datetime import date
from decimal import Decimal
from pathlib import Path

from app.domain.models import CsvErrorCode
from app.services.csv_reader import read_csv_bytes
from app.services.normalizer import normalize_csv_result

MAX_SIZE = 5 * 1024 * 1024
MAX_ROWS = 10_000


def normalize(data: bytes):
    read_result = read_csv_bytes(
        data,
        max_file_size=MAX_SIZE,
        max_rows=MAX_ROWS,
    )
    return normalize_csv_result(read_result)


def test_valid_sample_normalizes_all_rows() -> None:
    result = normalize(Path("sample_data/valid_sales.csv").read_bytes())

    assert result.is_valid is True
    assert result.total_rows == 12
    assert result.valid_count == 12
    assert result.invalid_count == 0
    assert result.errors == ()


def test_normalizes_types_defaults_strings_and_sales_exactly() -> None:
    data = (
        b"date,product,category,region,quantity,unit_price,discount,customer_type\n"
        b"2026-01-15,  Desk  Lamp  , Office , North ,3,100.50,,   \n"
    )
    result = normalize(data)
    row = result.valid_rows[0]

    assert row.row_number == 2
    assert row.date == date(2026, 1, 15)
    assert row.product == "Desk  Lamp"
    assert row.category == "Office"
    assert row.region == "North"
    assert row.quantity == 3
    assert row.unit_price == Decimal("100.50")
    assert row.discount == Decimal("0")
    assert row.customer_type is None
    assert row.sales == Decimal("301.50")


def test_sales_supports_zero_and_full_discount_without_rounding() -> None:
    data = (
        b"date,product,category,region,quantity,unit_price,discount\n"
        b"2026-01-15,A,Office,North,0,100.55,0\n"
        b"2026-01-16,B,Office,North,3,100.55,1\n"
        b"2026-01-17,C,Office,North,3,100.55,0.1\n"
    )
    result = normalize(data)

    assert [row.sales for row in result.valid_rows] == [
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("271.485"),
    ]


def test_optional_columns_can_be_absent() -> None:
    data = (
        b"date,product,category,region,quantity,unit_price\n"
        b"2026-01-15,A,Office,North,1,10\n"
    )
    row = normalize(data).valid_rows[0]

    assert row.discount == Decimal("0")
    assert row.customer_type is None


def test_partial_success_retains_valid_rows_and_counts_invalid_rows() -> None:
    data = (
        b"date,product,category,region,quantity,unit_price\n"
        b"2026-01-15,A,Office,North,1,10\n"
        b"2026-01-16,B,Office,North,-1,abc\n"
    )
    result = normalize(data)

    assert result.is_valid is False
    assert result.valid_count == 1
    assert result.invalid_count == 1
    assert len(result.valid_rows) == 1
    assert {error.code for error in result.errors} == {
        CsvErrorCode.NEGATIVE_QUANTITY,
        CsvErrorCode.INVALID_NUMBER,
    }


def test_all_invalid_rows_adds_no_valid_rows_file_error() -> None:
    data = (
        b"date,product,category,region,quantity,unit_price\n"
        b"bad,,Office,North,-1,abc\n"
    )
    result = normalize(data)

    assert result.valid_count == 0
    assert result.invalid_count == 1
    assert CsvErrorCode.NO_VALID_ROWS in {error.code for error in result.errors}


def test_structural_failure_is_forwarded_without_value_conversion() -> None:
    result = normalize(b"")

    assert result.is_valid is False
    assert result.errors[0].code is CsvErrorCode.EMPTY_FILE
