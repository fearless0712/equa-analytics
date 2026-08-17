import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from app.domain.models import BusinessInsight, InsightType

DISPLAY_PRECISION = Decimal("0.01")
PERCENT_VALUE_PATTERN = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?%")


def _finite_decimal(value: Decimal | int | None) -> Decimal | None:
    if value is None:
        return None
    converted = value if isinstance(value, Decimal) else Decimal(value)
    return converted if converted.is_finite() else None


def _rounded(value: Decimal | int | None) -> Decimal | None:
    converted = _finite_decimal(value)
    if converted is None:
        return None
    try:
        return converted.quantize(DISPLAY_PRECISION, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def _grouped(value: Decimal, *, fixed_decimals: bool) -> str:
    if fixed_decimals:
        return f"{value:,.2f}"
    return f"{value:,.0f}"


def format_number(value: Decimal | int | None) -> str:
    rounded = _rounded(value)
    if rounded is None:
        return "N/A"
    return _grouped(rounded, fixed_decimals=rounded != rounded.to_integral_value())


def format_money(value: Decimal | int | None) -> str:
    return format_number(value)


def format_decimal(value: Decimal | int | None) -> str:
    return format_number(value)


def format_integer(value: int | None) -> str:
    return "N/A" if value is None else f"{value:,}"


def format_percentage(value: Decimal | None) -> str:
    converted = _finite_decimal(value)
    return "N/A" if converted is None else f"{converted.quantize(DISPLAY_PRECISION, rounding=ROUND_HALF_UP):,.2f}%"


def format_ratio(value: Decimal | None) -> str:
    converted = _finite_decimal(value)
    return format_percentage(None if converted is None else converted * Decimal("100"))


def format_signed_number(value: Decimal | int | None) -> str:
    rounded = _rounded(value)
    if rounded is None:
        return "N/A"
    prefix = "+" if rounded > 0 else ""
    return f"{prefix}{_grouped(rounded, fixed_decimals=rounded != rounded.to_integral_value())}"


def format_signed_percentage(value: Decimal | None) -> str:
    converted = _finite_decimal(value)
    if converted is None:
        return "N/A"
    rounded = converted.quantize(DISPLAY_PRECISION, rounding=ROUND_HALF_UP)
    prefix = "+" if rounded > 0 else ""
    return f"{prefix}{rounded:,.2f}%"


def format_insight_summary(insight: BusinessInsight) -> str:
    if insight.type not in {
        InsightType.SALES_GROWTH,
        InsightType.SALES_DECLINE,
        InsightType.SALES_STABLE,
        InsightType.CONCENTRATION,
    }:
        return insight.summary
    return PERCENT_VALUE_PATTERN.sub(
        lambda match: format_percentage(Decimal(match.group()[:-1])),
        insight.summary,
    )
