from pathlib import Path

import pytest

from app.domain.models import CsvErrorCode
from app.services.csv_reader import read_csv_bytes

HEADER = b"date,product,category,region,quantity,unit_price\n"
ROW = b"2026-01-03,Desk Lamp,Office,North,3,4200\n"
MAX_SIZE = 5 * 1024 * 1024
MAX_ROWS = 10_000


def read(data: bytes, *, max_size: int = MAX_SIZE, max_rows: int = MAX_ROWS):
    return read_csv_bytes(data, max_file_size=max_size, max_rows=max_rows)


def assert_error(data: bytes, expected: CsvErrorCode) -> None:
    result = read(data)

    assert result.validation.is_valid is False
    assert expected in {error.code for error in result.validation.errors}


def test_reads_valid_sample_with_physical_row_numbers() -> None:
    sample = Path("sample_data/valid_sales.csv").read_bytes()
    result = read(sample)

    assert result.validation.is_valid is True
    assert result.total_rows == 12
    assert result.rows[0].row_number == 2
    assert result.encoding == "utf-8"


def test_reads_utf8_bom_transparently() -> None:
    result = read(b"\xef\xbb\xbf" + HEADER + ROW)

    assert result.validation.is_valid is True
    assert result.normalized_headers[0] == "date"
    assert result.encoding == "utf-8-sig"


def test_multiline_record_uses_its_starting_physical_line() -> None:
    data = HEADER + b'2026-01-03,"Desk\nLamp",Office,North,3,4200\n'
    result = read(data)

    assert result.validation.is_valid is True
    assert result.rows[0].row_number == 2


@pytest.mark.parametrize("data", [b"", b"\xef\xbb\xbf", b"   ", b"\r\n\n"])
def test_rejects_empty_file_variants(data: bytes) -> None:
    assert_error(data, CsvErrorCode.EMPTY_FILE)


def test_rejects_invalid_utf8_without_exception_details() -> None:
    result = read(b"\x81\xff")

    assert result.validation.errors[0].code is CsvErrorCode.INVALID_ENCODING
    assert result.validation.errors[0].message == "The CSV file must use UTF-8 encoding."


def test_rejects_nul_byte_with_dedicated_code() -> None:
    assert_error(HEADER + ROW + b"\x00", CsvErrorCode.NUL_BYTE)


def test_allows_exact_file_size() -> None:
    row_start = b"2026-01-03,"
    row_end = b",Office,North,1,1\n"
    padding = b"A" * (MAX_SIZE - len(HEADER) - len(row_start) - len(row_end))
    result = read(HEADER + row_start + padding + row_end)

    assert result.validation.is_valid is True
    assert result.total_rows == 1


def test_rejects_one_byte_over_file_size_before_parsing() -> None:
    result = read(b"x" * (MAX_SIZE + 1))

    assert result.validation.errors[0].code is CsvErrorCode.FILE_TOO_LARGE
    assert result.encoding is None


def test_rejects_headerless_content() -> None:
    result = read(b"2026-01-03,Desk Lamp,Office,North,3,4200\n")

    codes = {error.code for error in result.validation.errors}
    assert CsvErrorCode.MISSING_REQUIRED_COLUMN in codes
    assert CsvErrorCode.UNKNOWN_COLUMN in codes


def test_rejects_header_without_data() -> None:
    assert_error(HEADER, CsvErrorCode.NO_VALID_ROWS)


@pytest.mark.parametrize(
    ("fixture_name", "code"),
    [
        ("missing_required_column.csv", CsvErrorCode.MISSING_REQUIRED_COLUMN),
        ("duplicate_column.csv", CsvErrorCode.DUPLICATE_COLUMN),
        ("unknown_column.csv", CsvErrorCode.UNKNOWN_COLUMN),
    ],
)
def test_reuses_structural_error_fixtures(
    fixture_name: str, code: CsvErrorCode
) -> None:
    data = (Path("tests/fixtures") / fixture_name).read_bytes()

    assert_error(data, code)


def test_rejects_normalized_duplicate_header() -> None:
    data = (
        b"date,Product, PRODUCT ,category,region,quantity,unit_price\n"
        b"2026-01-03,Desk Lamp,Desk Lamp,Office,North,1,4200\n"
    )
    assert_error(data, CsvErrorCode.DUPLICATE_COLUMN)


def test_rejects_broken_quote_without_parser_detail() -> None:
    result = read(HEADER + b'2026-01-03,"Desk Lamp,Office,North,1,4200\n')

    assert result.validation.errors[0].code is CsvErrorCode.PARSE_ERROR
    assert result.validation.errors[0].message == "The CSV file could not be parsed."


@pytest.mark.parametrize(
    "row",
    [
        b"2026-01-03,Desk Lamp,Office,North,3\n",
        b"2026-01-03,Desk Lamp,Office,North,3,4200,extra\n",
    ],
)
def test_rejects_inconsistent_column_count(row: bytes) -> None:
    result = read(HEADER + row)

    assert result.validation.errors[0].code is CsvErrorCode.PARSE_ERROR
    assert result.validation.errors[0].row == 2


def test_allows_exact_row_limit() -> None:
    result = read(HEADER + ROW * MAX_ROWS)

    assert result.validation.is_valid is True
    assert result.total_rows == MAX_ROWS


def test_stops_at_first_row_over_limit() -> None:
    result = read(HEADER + ROW * (MAX_ROWS + 1))

    assert result.validation.errors[0].code is CsvErrorCode.TOO_MANY_ROWS
    assert result.total_rows == MAX_ROWS + 1
    assert result.validation.valid_rows == MAX_ROWS
    assert result.validation.errors[0].row == MAX_ROWS + 2


def test_step_four_value_errors_are_not_checked_yet() -> None:
    negative_quantity = Path("tests/fixtures/negative_quantity.csv").read_bytes()

    assert read(negative_quantity).validation.is_valid is True
