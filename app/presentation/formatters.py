import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from app.domain.models import BusinessInsight, InsightType

DISPLAY_PRECISION = Decimal("0.01")
PERCENT_VALUE_PATTERN = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?%")
LONG_DECIMAL_PATTERN = re.compile(r"(?<![\w.])-?\d+\.\d{3,}(?![\w.])")
EVIDENCE_LABELS = {
    "top_one_share": "Leading share",
    "top_three_share": "Top three share",
    "significant_change_pct": "Significant change threshold",
    "minimum_total_sales_share_pct": "Minimum total sales share",
    "lower_bound": "Lower bound",
    "upper_bound": "Upper bound",
    "change_amount": "Change amount",
    "change_pct": "Change percentage",
    "significant": "Significant",
}


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


def _evidence_value(key: str, raw_value: str) -> str:
    normalized = raw_value.strip()
    if not normalized or normalized.lower() in {"none", "null", "n/a"}:
        return "N/A"
    if normalized.lower() in {"true", "false"}:
        return normalized.lower()
    try:
        number = Decimal(normalized)
    except InvalidOperation:
        return normalized
    if "share" in key or "pct" in key or "percentage" in key:
        return format_percentage(number)
    if key == "change_amount":
        return format_signed_number(number)
    return format_decimal(number)


def format_insight_evidence(evidence: tuple[str, ...]) -> tuple[str, ...]:
    formatted: list[str] = []
    for item in evidence:
        for part in item.split(";"):
            value = part.strip()
            if not value:
                continue
            key, separator, raw_value = value.partition("=")
            if not separator:
                formatted.append(value)
                continue
            normalized_key = key.strip().lower()
            label = EVIDENCE_LABELS.get(
                normalized_key,
                normalized_key.replace("_", " ").strip().title() or "Evidence",
            )
            formatted.append(
                f"{label}: {_evidence_value(normalized_key, raw_value)}"
            )
    return tuple(formatted)


def format_ai_evidence(value: str) -> str:
    """Format numeric display tokens in untrusted AI evidence as plain text."""
    parts = [part.strip() for part in value.split(";") if part.strip()]
    if parts and all("=" in part for part in parts):
        return "; ".join(format_insight_evidence(tuple(parts)))

    formatted = PERCENT_VALUE_PATTERN.sub(
        lambda match: format_percentage(Decimal(match.group()[:-1])), value
    )
    return LONG_DECIMAL_PATTERN.sub(
        lambda match: format_decimal(Decimal(match.group())), formatted
    )
