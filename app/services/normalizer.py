from datetime import date
from decimal import Decimal, localcontext

from app.domain.csv_spec import MAX_NUMERIC_TEXT_LENGTH
from app.domain.models import (
    CsvErrorCode,
    CsvNormalizationResult,
    CsvReadResult,
    CsvValidationError,
    NormalizedSalesRow,
)
from app.services.value_validator import validate_row_values


def _normalize_valid_row(
    values: dict[str, str], row_number: int
) -> NormalizedSalesRow:
    quantity = int(values["quantity"].strip())
    unit_price = Decimal(values["unit_price"].strip())
    discount = Decimal(values.get("discount", "").strip() or "0")
    with localcontext() as context:
        context.prec = MAX_NUMERIC_TEXT_LENGTH * 3
        sales = Decimal(quantity) * unit_price * (Decimal("1") - discount)
    customer_type = values.get("customer_type", "").strip() or None

    return NormalizedSalesRow(
        row_number=row_number,
        date=date.fromisoformat(values["date"].strip()),
        product=values["product"].strip(),
        category=values["category"].strip(),
        region=values["region"].strip(),
        quantity=quantity,
        unit_price=unit_price,
        discount=discount,
        customer_type=customer_type,
        sales=sales,
    )


def normalize_csv_result(read_result: CsvReadResult) -> CsvNormalizationResult:
    if not read_result.validation.is_valid:
        return CsvNormalizationResult(
            errors=read_result.validation.errors,
            total_rows=read_result.total_rows,
            valid_count=0,
            invalid_count=read_result.validation.invalid_rows,
            is_valid=False,
        )

    valid_rows: list[NormalizedSalesRow] = []
    errors: list[CsvValidationError] = []
    invalid_count = 0

    for raw_row in read_result.rows:
        values = dict(zip(read_result.normalized_headers, raw_row.values, strict=True))
        row_errors = validate_row_values(values, raw_row.row_number)
        if row_errors:
            errors.extend(row_errors)
            invalid_count += 1
            continue
        valid_rows.append(_normalize_valid_row(values, raw_row.row_number))

    if not valid_rows:
        errors.append(CsvValidationError(code=CsvErrorCode.NO_VALID_ROWS))

    return CsvNormalizationResult(
        valid_rows=tuple(valid_rows),
        errors=tuple(errors),
        total_rows=read_result.total_rows,
        valid_count=len(valid_rows),
        invalid_count=invalid_count,
        is_valid=not errors,
    )
