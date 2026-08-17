import csv
from pathlib import Path

from app.config import Settings
from app.domain.csv_spec import (
    ALLOWED_COLUMNS,
    CSV_COLUMN_SPECS,
    CSV_HEADER_NORMALIZATION,
    OPTIONAL_COLUMNS,
    REQUIRED_COLUMNS,
    SALES_FORMULA,
    SALES_FORMULA_FIELDS,
    SUPPORTED_CSV_ENCODINGS,
    normalize_csv_column_name,
)
from app.domain.models import CsvErrorCode, CsvValidationError, CsvValidationResult

EXPECTED_ERROR_CODES = {
    "CSV_EMPTY_FILE",
    "CSV_FILE_TOO_LARGE",
    "CSV_INVALID_FILE_TYPE",
    "CSV_INVALID_ENCODING",
    "CSV_NUL_BYTE",
    "CSV_PARSE_ERROR",
    "CSV_TOO_MANY_ROWS",
    "CSV_MISSING_REQUIRED_COLUMN",
    "CSV_DUPLICATE_COLUMN",
    "CSV_UNKNOWN_COLUMN",
    "CSV_INVALID_DATE",
    "CSV_INVALID_NUMBER",
    "CSV_INVALID_QUANTITY",
    "CSV_NEGATIVE_QUANTITY",
    "CSV_NEGATIVE_UNIT_PRICE",
    "CSV_UNIT_PRICE_TOO_LARGE",
    "CSV_INVALID_DISCOUNT",
    "CSV_EMPTY_PRODUCT",
    "CSV_EMPTY_CATEGORY",
    "CSV_EMPTY_REGION",
    "CSV_STRING_TOO_LONG",
    "CSV_NO_VALID_ROWS",
}


def test_column_collections_are_the_canonical_contract() -> None:
    assert REQUIRED_COLUMNS == (
        "date",
        "product",
        "category",
        "region",
        "quantity",
        "unit_price",
    )
    assert OPTIONAL_COLUMNS == ("discount", "customer_type")
    assert ALLOWED_COLUMNS == REQUIRED_COLUMNS + OPTIONAL_COLUMNS
    assert tuple(spec.name for spec in CSV_COLUMN_SPECS) == ALLOWED_COLUMNS


def test_header_normalization_contract() -> None:
    assert SUPPORTED_CSV_ENCODINGS == ("utf-8", "utf-8-sig")
    assert CSV_HEADER_NORMALIZATION == ("remove_bom", "strip", "lowercase")
    assert normalize_csv_column_name("\ufeff Date ") == "date"
    assert normalize_csv_column_name("PRODUCT") == "product"


def test_column_type_and_range_specs() -> None:
    specs = {spec.name: spec for spec in CSV_COLUMN_SPECS}

    assert specs["date"].value_type == "date"
    assert specs["product"].value_type == "string"
    assert specs["quantity"].minimum == 0
    assert specs["unit_price"].minimum == 0
    assert specs["discount"].minimum == 0
    assert specs["discount"].maximum == 1
    assert specs["discount"].default_value == 0


def test_error_code_catalog_is_complete() -> None:
    assert {code.value for code in CsvErrorCode} == EXPECTED_ERROR_CODES


def test_validation_error_uses_safe_catalog_message() -> None:
    error = CsvValidationError(
        code=CsvErrorCode.NEGATIVE_QUANTITY,
        field="quantity",
        row=12,
    )

    assert error.model_dump() == {
        "code": CsvErrorCode.NEGATIVE_QUANTITY,
        "field": "quantity",
        "row": 12,
        "message": "Quantity must be zero or greater.",
    }


def test_validation_error_allows_null_location() -> None:
    error = CsvValidationError(code=CsvErrorCode.EMPTY_FILE)

    assert error.field is None
    assert error.row is None


def test_validation_result_holds_summary() -> None:
    error = CsvValidationError(code=CsvErrorCode.INVALID_DATE, field="date", row=2)
    result = CsvValidationResult(
        is_valid=False,
        errors=(error,),
        total_rows=3,
        valid_rows=2,
        invalid_rows=1,
    )

    assert result.errors == (error,)
    assert result.total_rows == result.valid_rows + result.invalid_rows


def test_sales_formula_is_the_phase_one_contract() -> None:
    assert SALES_FORMULA == "quantity * unit_price * (1 - discount)"
    assert SALES_FORMULA_FIELDS == ("quantity", "unit_price", "discount")


def test_default_csv_limits() -> None:
    settings = Settings(_env_file=None)

    assert settings.max_csv_file_size == 5 * 1024 * 1024
    assert settings.max_csv_rows == 10_000


def test_sample_csv_is_synthetic_and_matches_contract() -> None:
    sample_path = Path(__file__).parents[1] / "sample_data" / "valid_sales.csv"
    with sample_path.open(encoding="utf-8", newline="") as sample_file:
        rows = list(csv.DictReader(sample_file))

    assert tuple(rows[0]) == ALLOWED_COLUMNS
    assert 10 <= len(rows) <= 15
    assert len({row["product"] for row in rows}) > 1
    assert len({row["category"] for row in rows}) > 1
    assert len({row["region"] for row in rows}) > 1
    assert len({row["date"][:7] for row in rows}) > 1
    assert any(row["discount"] == "0" for row in rows)
    assert any(row["discount"] == "" for row in rows)
    assert any(row["discount"] not in {"", "0"} for row in rows)
    assert all("@" not in value for row in rows for value in row.values())


def test_invalid_csv_fixtures_are_complete_and_synthetic() -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    expected_names = {
        "missing_required_column.csv",
        "negative_quantity.csv",
        "negative_unit_price.csv",
        "discount_over_one.csv",
        "invalid_date.csv",
        "empty_product.csv",
        "empty_category.csv",
        "empty_region.csv",
        "duplicate_column.csv",
        "unknown_column.csv",
    }

    fixtures = {path.name for path in fixture_dir.glob("*.csv")}
    fixture_contents = "".join(
        path.read_text(encoding="utf-8") for path in fixture_dir.glob("*.csv")
    )

    assert fixtures == expected_names
    assert "@" not in fixture_contents
