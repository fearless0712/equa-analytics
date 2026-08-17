from app.domain.models import CsvErrorCode
from app.services.csv_validator import validate_csv_headers


def test_header_validation_normalizes_and_accepts_column_order() -> None:
    headers, errors = validate_csv_headers(
        [" UNIT_PRICE ", "PRODUCT", "date", "region", "category", "quantity"]
    )

    assert headers == (
        "unit_price",
        "product",
        "date",
        "region",
        "category",
        "quantity",
    )
    assert errors == ()


def test_header_validation_collects_missing_and_unknown_columns() -> None:
    _, errors = validate_csv_headers(
        ["date", "product", "category", "quantity", "unit_price", "foo"]
    )

    assert [(error.code, error.field) for error in errors] == [
        (CsvErrorCode.MISSING_REQUIRED_COLUMN, "region"),
        (CsvErrorCode.UNKNOWN_COLUMN, "foo"),
    ]


def test_header_validation_detects_duplicates_after_normalization() -> None:
    _, errors = validate_csv_headers(
        [
            "date",
            "Product",
            " PRODUCT ",
            "category",
            "region",
            "quantity",
            "unit_price",
        ]
    )

    duplicate_errors = [
        error for error in errors if error.code is CsvErrorCode.DUPLICATE_COLUMN
    ]
    assert len(duplicate_errors) == 1
    assert duplicate_errors[0].field == "product"


def test_header_validation_rejects_empty_header() -> None:
    _, errors = validate_csv_headers(
        ["date", "product", "", "region", "quantity", "unit_price"]
    )

    assert errors[0].code is CsvErrorCode.PARSE_ERROR
    assert errors[0].row == 1
