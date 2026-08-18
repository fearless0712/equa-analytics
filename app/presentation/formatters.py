import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from app.domain.models import BusinessInsight, InsightType

DISPLAY_PRECISION = Decimal("0.01")
PERCENT_VALUE_PATTERN = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?%")
AI_EVIDENCE_METRIC_PATTERN = re.compile(
    r"^(?:(?P<label>.+?)\s+)?(?P<key>sales_share|[a-z][a-z0-9_]*_share|"
    r"change_pct|[a-z][a-z0-9_]*_pct|percentage|unit_price|change_amount|"
    r"amount|quantity|sales|share)\s+"
    r"(?:(?:is|was)(?:\s+reported\s+as)?\s+)?"
    r"(?P<value>-?\d+(?:\.\d+)?)\.?$",
    re.IGNORECASE,
)
AI_EVIDENCE_SALES_COMPARISON_PATTERN = re.compile(
    r"^(?P<label>.+?)\s+sales\s+(?P<current>-?\d+(?:\.\d+)?)\s+"
    r"versus\s+(?P<previous>-?\d+(?:\.\d+)?)\s+previously\.?$",
    re.IGNORECASE,
)
AI_EVIDENCE_SEVERITY_PATTERN = re.compile(
    r"^severity\s+(?P<value>[a-z][a-z_-]*)\.?$", re.IGNORECASE
)
AI_EVIDENCE_NUMBER_PATTERN = re.compile(r"^-?\d+(?:\.\d+)?$")
AI_EVIDENCE_KEY_VALUE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\s*=", re.IGNORECASE)
AI_EVIDENCE_PATH_PATTERN = re.compile(
    r"^(?:dimensions\.)?(?P<collection>monthly|products|categories|regions)"
    r"\[(?P<label>[^\]\r\n]{1,240})\]\."
    r"(?P<key>sales_change_pct|sales_share|current_value|previous_value|"
    r"sales_change_amount|change_amount|sales|quantity|unit_price)"
    r"(?:\s*=\s*|\s+)(?P<value>-?\d+(?:\.\d+)?)(?:\.\.\.|\.?)$",
    re.IGNORECASE,
)
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
    if parts and all(AI_EVIDENCE_KEY_VALUE_PATTERN.match(part) for part in parts):
        return "; ".join(format_insight_evidence(tuple(parts)))

    def format_known_pattern(text: str) -> str:
        leading = text[: len(text) - len(text.lstrip())]
        trailing = text[len(text.rstrip()) :]
        candidate = text.strip()

        path_value = AI_EVIDENCE_PATH_PATTERN.fullmatch(candidate)
        if path_value:
            collection = path_value.group("collection").lower()
            key = path_value.group("key").lower()
            number = Decimal(path_value.group("value"))
            if "share" in key:
                formatted = format_percentage(number)
            elif "pct" in key:
                formatted = format_signed_percentage(number)
            elif "change_amount" in key:
                formatted = format_signed_number(number)
            else:
                formatted = format_decimal(number)
            human_key = key.replace("_pct", "").replace("_", " ")
            label = "" if collection == "monthly" else f"{path_value.group('label')} "
            return (
                f"{leading}{label}{human_key.capitalize() if not label else human_key}: "
                f"{formatted}{trailing}"
            )

        comparison = AI_EVIDENCE_SALES_COMPARISON_PATTERN.fullmatch(candidate)
        if comparison:
            current = format_decimal(Decimal(comparison.group("current")))
            previous = format_decimal(Decimal(comparison.group("previous")))
            return (
                f"{leading}{comparison.group('label')} sales {current} versus "
                f"{previous} previously{trailing}"
            )

        metric = AI_EVIDENCE_METRIC_PATTERN.fullmatch(candidate)
        if metric:
            key = metric.group("key").lower()
            number = Decimal(metric.group("value"))
            formatted = (
                format_percentage(number)
                if "share" in key or "pct" in key or key == "percentage"
                else format_decimal(number)
            )
            human_key = key.replace("_", " ")
            label = f"{metric.group('label')} " if metric.group("label") else ""
            return (
                f"{leading}{label}{human_key.capitalize() if not label else human_key}: "
                f"{formatted}{trailing}"
            )

        severity = AI_EVIDENCE_SEVERITY_PATTERN.fullmatch(candidate)
        if severity:
            return f"{leading}Severity: {severity.group('value')}{trailing}"

        if AI_EVIDENCE_NUMBER_PATTERN.fullmatch(candidate):
            return f"{leading}{format_decimal(Decimal(candidate))}{trailing}"
        return text

    segments = re.split(r"(;\s*)", value)
    return "".join(
        segment if index % 2 else format_known_pattern(segment)
        for index, segment in enumerate(segments)
    )
