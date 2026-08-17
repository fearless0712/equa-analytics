import re
from datetime import date
from decimal import Decimal
from typing import Mapping

from app.domain.csv_spec import (
    MAX_NUMERIC_TEXT_LENGTH,
    MAX_QUANTITY,
    MAX_TEXT_LENGTH,
    MAX_UNIT_PRICE,
)
from app.domain.models import CsvErrorCode, CsvValidationError

DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
INTEGER_PATTERN = re.compile(r"-?\d+\Z")
DECIMAL_PATTERN = re.compile(r"-?\d+(?:\.\d+)?\Z")

REQUIRED_TEXT_ERRORS = {
    "product": CsvErrorCode.EMPTY_PRODUCT,
    "category": CsvErrorCode.EMPTY_CATEGORY,
    "region": CsvErrorCode.EMPTY_REGION,
}


def _error(code: CsvErrorCode, field: str, row: int) -> CsvValidationError:
    return CsvValidationError(code=code, field=field, row=row)


def _is_decimal_literal(value: str) -> bool:
    return (
        len(value) <= MAX_NUMERIC_TEXT_LENGTH
        and DECIMAL_PATTERN.fullmatch(value) is not None
    )


def validate_row_values(
    values: Mapping[str, str], row_number: int
) -> tuple[CsvValidationError, ...]:
    errors: list[CsvValidationError] = []

    date_value = values.get("date", "").strip()
    try:
        if not DATE_PATTERN.fullmatch(date_value):
            raise ValueError
        date.fromisoformat(date_value)
    except ValueError:
        errors.append(_error(CsvErrorCode.INVALID_DATE, "date", row_number))

    for field, code in REQUIRED_TEXT_ERRORS.items():
        value = values.get(field, "").strip()
        if not value:
            errors.append(_error(code, field, row_number))
        elif len(value) > MAX_TEXT_LENGTH:
            errors.append(_error(CsvErrorCode.STRING_TOO_LONG, field, row_number))

    customer_type = values.get("customer_type", "").strip()
    if customer_type and len(customer_type) > MAX_TEXT_LENGTH:
        errors.append(
            _error(CsvErrorCode.STRING_TOO_LONG, "customer_type", row_number)
        )

    quantity_value = values.get("quantity", "").strip()
    if len(quantity_value) > MAX_NUMERIC_TEXT_LENGTH or not INTEGER_PATTERN.fullmatch(
        quantity_value
    ):
        if _is_decimal_literal(quantity_value):
            errors.append(
                _error(CsvErrorCode.INVALID_QUANTITY, "quantity", row_number)
            )
        else:
            errors.append(_error(CsvErrorCode.INVALID_NUMBER, "quantity", row_number))
    else:
        quantity = int(quantity_value)
        if quantity < 0:
            errors.append(
                _error(CsvErrorCode.NEGATIVE_QUANTITY, "quantity", row_number)
            )
        elif quantity > MAX_QUANTITY:
            errors.append(
                _error(CsvErrorCode.INVALID_QUANTITY, "quantity", row_number)
            )

    unit_price_value = values.get("unit_price", "").strip()
    if not _is_decimal_literal(unit_price_value):
        errors.append(_error(CsvErrorCode.INVALID_NUMBER, "unit_price", row_number))
    else:
        unit_price = Decimal(unit_price_value)
        if unit_price < 0:
            errors.append(
                _error(CsvErrorCode.NEGATIVE_UNIT_PRICE, "unit_price", row_number)
            )
        elif unit_price > MAX_UNIT_PRICE:
            errors.append(
                _error(CsvErrorCode.UNIT_PRICE_TOO_LARGE, "unit_price", row_number)
            )

    discount_value = values.get("discount", "").strip()
    if discount_value:
        if not _is_decimal_literal(discount_value):
            errors.append(
                _error(CsvErrorCode.INVALID_DISCOUNT, "discount", row_number)
            )
        else:
            discount = Decimal(discount_value)
            if discount < 0 or discount > 1:
                errors.append(
                    _error(CsvErrorCode.INVALID_DISCOUNT, "discount", row_number)
                )

    return tuple(errors)
