from collections import Counter

from app.domain.csv_spec import (
    ALLOWED_COLUMNS,
    REQUIRED_COLUMNS,
    normalize_csv_column_name,
)
from app.domain.models import CsvErrorCode, CsvValidationError


def validate_csv_headers(
    headers: list[str],
) -> tuple[tuple[str, ...], tuple[CsvValidationError, ...]]:
    normalized = tuple(normalize_csv_column_name(header) for header in headers)
    errors: list[CsvValidationError] = []

    if not normalized or any(not header for header in normalized):
        errors.append(CsvValidationError(code=CsvErrorCode.PARSE_ERROR, row=1))

    counts = Counter(header for header in normalized if header)
    errors.extend(
        CsvValidationError(
            code=CsvErrorCode.DUPLICATE_COLUMN,
            field=header,
            row=1,
        )
        for header in normalized
        if header and counts[header] > 1 and header not in {
            error.field for error in errors if error.code is CsvErrorCode.DUPLICATE_COLUMN
        }
    )
    errors.extend(
        CsvValidationError(
            code=CsvErrorCode.MISSING_REQUIRED_COLUMN,
            field=required,
            row=1,
        )
        for required in REQUIRED_COLUMNS
        if required not in normalized
    )
    errors.extend(
        CsvValidationError(
            code=CsvErrorCode.UNKNOWN_COLUMN,
            field=header,
            row=1,
        )
        for header in dict.fromkeys(normalized)
        if header and header not in ALLOWED_COLUMNS
    )

    return normalized, tuple(errors)
