from decimal import Decimal, localcontext

from app.domain.insight_config import (
    IQR_MULTIPLIER,
    MAX_OUTLIER_INSIGHTS,
    MAX_QUALITY_INSIGHTS,
    MIN_OUTLIER_SAMPLE_SIZE,
)
from app.domain.models import (
    AnalysisMetadata,
    AnalysisResult,
    BusinessInsight,
    InsightSeverity,
    InsightType,
    NormalizedSalesRow,
)
from app.services.kpi_calculator import DECIMAL_PRECISION


def build_analysis_metadata(
    analysis: AnalysisResult, rows: tuple[NormalizedSalesRow, ...]
) -> AnalysisMetadata:
    dates = [row.date for row in rows]
    return AnalysisMetadata(
        date_from=min(dates) if dates else None,
        date_to=max(dates) if dates else None,
        observed_months=sum(not metric.is_imputed for metric in analysis.monthly),
        imputed_months=sum(metric.is_imputed for metric in analysis.monthly),
        row_count=len(rows),
        product_count=analysis.kpis.unique_products,
        category_count=analysis.kpis.unique_categories,
        region_count=analysis.kpis.unique_regions,
    )


def detect_quality_insights(
    analysis: AnalysisResult, metadata: AnalysisMetadata
) -> tuple[BusinessInsight, ...]:
    quality = analysis.quality
    insights: list[BusinessInsight] = []

    if quality.invalid_rows:
        insights.append(
            BusinessInsight(
                id="quality-invalid-rows",
                type=InsightType.DATA_QUALITY,
                severity=InsightSeverity.CRITICAL,
                title="Invalid rows detected",
                summary=f"{quality.invalid_rows} rows failed validation and were excluded from analysis.",
                metric_name="invalid_rows",
                current_value=quality.invalid_rows,
            )
        )
    if quality.duplicate_rows:
        insights.append(
            BusinessInsight(
                id="quality-duplicate-rows",
                type=InsightType.DATA_QUALITY,
                severity=InsightSeverity.WARNING,
                title="Duplicate rows detected",
                summary=f"{quality.duplicate_rows} duplicate rows were detected and retained in all calculations.",
                metric_name="duplicate_rows",
                current_value=quality.duplicate_rows,
            )
        )
    if quality.missing_optional_values:
        insights.append(
            BusinessInsight(
                id="quality-missing-optional",
                type=InsightType.DATA_QUALITY,
                severity=InsightSeverity.INFO,
                title="Optional values are missing",
                summary=f"{quality.missing_optional_values} rows have no customer type; this optional field does not block analysis.",
                metric_name="missing_optional_values",
                current_value=quality.missing_optional_values,
            )
        )
    if metadata.imputed_months:
        insights.append(
            BusinessInsight(
                id="quality-imputed-months",
                type=InsightType.DATA_GAP,
                severity=InsightSeverity.WARNING,
                title="Months without source rows",
                summary=f"{metadata.imputed_months} calendar months had no source rows and were shown as imputed zero values.",
                metric_name="imputed_months",
                current_value=metadata.imputed_months,
            )
        )
    if metadata.row_count < MIN_OUTLIER_SAMPLE_SIZE:
        insights.append(
            BusinessInsight(
                id="quality-limited-sample",
                type=InsightType.INSUFFICIENT_DATA,
                severity=InsightSeverity.INFO,
                title="Limited sample size",
                summary=f"Only {metadata.row_count} rows are available; potential outlier detection requires at least {MIN_OUTLIER_SAMPLE_SIZE} rows.",
                metric_name="row_count",
                current_value=metadata.row_count,
            )
        )

    return tuple(insights[:MAX_QUALITY_INSIGHTS])


def _quartile(values: list[Decimal], percentile: Decimal) -> Decimal:
    position = Decimal(len(values) - 1) * percentile
    lower_index = int(position)
    fraction = position - lower_index
    if fraction == 0:
        return values[lower_index]
    return values[lower_index] + (
        values[lower_index + 1] - values[lower_index]
    ) * fraction


def _metric_outlier_insight(
    metric_name: str, values: list[Decimal]
) -> BusinessInsight | None:
    if len(values) < MIN_OUTLIER_SAMPLE_SIZE:
        return None
    ordered = sorted(values)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        q1 = _quartile(ordered, Decimal("0.25"))
        q3 = _quartile(ordered, Decimal("0.75"))
        iqr = q3 - q1
        if iqr == 0:
            return None
        lower = q1 - IQR_MULTIPLIER * iqr
        upper = q3 + IQR_MULTIPLIER * iqr
        count = sum(value < lower or value > upper for value in ordered)
    if not count:
        return None
    label = metric_name.replace("_", " ")
    return BusinessInsight(
        id=f"outlier-{metric_name}",
        type=InsightType.POTENTIAL_OUTLIER,
        severity=InsightSeverity.WARNING,
        title=f"Potential {label} outliers",
        summary=f"{count} potential outliers were detected in {label} using the IQR rule; all rows were retained.",
        metric_name=metric_name,
        current_value=count,
        evidence=(f"lower_bound={lower}", f"upper_bound={upper}"),
    )


def detect_outlier_insights(
    rows: tuple[NormalizedSalesRow, ...]
) -> tuple[BusinessInsight, ...]:
    metrics = (
        ("sales", [row.sales for row in rows]),
        ("quantity", [Decimal(row.quantity) for row in rows]),
        ("unit_price", [row.unit_price for row in rows]),
    )
    insights = [
        insight
        for metric_name, values in metrics
        if (insight := _metric_outlier_insight(metric_name, values)) is not None
    ]
    return tuple(insights[:MAX_OUTLIER_INSIGHTS])
