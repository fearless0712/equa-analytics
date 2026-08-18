from datetime import datetime, timezone

from app.ai.models import AiInsightResponse
from app.domain.models import AnalysisResult, InsightCollection, MonthlyMetric
from app.domain.report_models import (
    BusinessReport,
    ReportAiStatus,
    ReportExecutiveSummary,
    ReportInsightSection,
    ReportMetadata,
    ReportMethodology,
    ReportTrend,
)

REPORT_MONTH_LIMIT = 36
REPORT_DIMENSION_LIMIT = 10


def _latest_observed_month(
    analysis: AnalysisResult,
) -> tuple[MonthlyMetric | None, ReportTrend]:
    observed_indexes = [
        index for index, metric in enumerate(analysis.monthly) if not metric.is_imputed
    ]
    if not observed_indexes:
        return None, ReportTrend.UNAVAILABLE
    latest_index = observed_indexes[-1]
    latest = analysis.monthly[latest_index]
    if latest_index == 0 or analysis.monthly[latest_index - 1].is_imputed:
        return latest, ReportTrend.UNAVAILABLE
    if latest.sales_change is None:
        return latest, ReportTrend.UNAVAILABLE
    if latest.sales_change > 0:
        return latest, ReportTrend.INCREASE
    if latest.sales_change < 0:
        return latest, ReportTrend.DECREASE
    return latest, ReportTrend.STABLE


def _executive_summary(
    analysis: AnalysisResult, insights: InsightCollection
) -> ReportExecutiveSummary:
    latest, trend = _latest_observed_month(analysis)
    date_from = insights.metadata.date_from
    date_to = insights.metadata.date_to
    if latest is None:
        headline = "No observed monthly performance is available for comparison."
    elif trend is ReportTrend.UNAVAILABLE:
        headline = (
            "Validated performance is available, but the latest observed month "
            "does not have a comparable preceding source month."
        )
    else:
        headline = (
            f"The latest comparable monthly sales trend is classified as {trend.value} "
            "from the supplied calculated results."
        )

    period_text = (
        f"The validated data covers {date_from.isoformat()} to {date_to.isoformat()}."
        if date_from and date_to
        else "The validated date range is unavailable."
    )
    observations = (
        period_text,
        (
            f"The analysis includes {analysis.kpis.transaction_count} validated transactions "
            f"across {analysis.kpis.unique_products} products, "
            f"{analysis.kpis.unique_categories} categories, and "
            f"{analysis.kpis.unique_regions} regions."
        ),
        (
            f"{insights.metadata.imputed_months} calendar months are explicitly marked "
            "as imputed zero values."
        ),
    )
    return ReportExecutiveSummary(
        headline=headline,
        observations=observations,
        total_sales=analysis.kpis.total_sales,
        latest_month=latest.year_month if latest else None,
        latest_sales=latest.sales if latest else None,
        latest_change_amount=(
            latest.sales_change if latest and trend is not ReportTrend.UNAVAILABLE else None
        ),
        latest_change_pct=(
            latest.sales_change_pct
            if latest and trend is not ReportTrend.UNAVAILABLE
            else None
        ),
        latest_trend=trend,
        leading_product=analysis.products[0].name if analysis.products else None,
        leading_category=analysis.categories[0].name if analysis.categories else None,
        leading_region=analysis.regions[0].name if analysis.regions else None,
    )


def build_business_report(
    analysis: AnalysisResult,
    insights: InsightCollection,
    *,
    ai: AiInsightResponse | None = None,
    ai_unavailable: bool = False,
    generated_at: datetime | None = None,
) -> BusinessReport:
    if ai is not None and ai_unavailable:
        raise ValueError("AI response and unavailable status are mutually exclusive")
    if ai is not None:
        ai_status = ReportAiStatus.INCLUDED
    elif ai_unavailable:
        ai_status = ReportAiStatus.UNAVAILABLE
    else:
        ai_status = ReportAiStatus.NOT_REQUESTED

    timestamp = generated_at or datetime.now(timezone.utc)
    return BusinessReport(
        metadata=ReportMetadata(
            generated_at=timestamp,
            date_from=insights.metadata.date_from,
            date_to=insights.metadata.date_to,
            observed_months=insights.metadata.observed_months,
            imputed_months=insights.metadata.imputed_months,
            total_rows=analysis.quality.total_rows,
            analyzed_rows=insights.metadata.row_count,
            potential_outliers=insights.metadata.potential_outliers,
        ),
        executive_summary=_executive_summary(analysis, insights),
        kpis=analysis.kpis,
        monthly=analysis.monthly[-REPORT_MONTH_LIMIT:],
        top_products=analysis.products[:REPORT_DIMENSION_LIMIT],
        top_categories=analysis.categories[:REPORT_DIMENSION_LIMIT],
        top_regions=analysis.regions[:REPORT_DIMENSION_LIMIT],
        largest_category_growth=analysis.largest_category_growth,
        largest_category_decline=analysis.largest_category_decline,
        insights=ReportInsightSection(
            business=insights.business_insights,
            quality=insights.quality_insights,
            outliers=insights.outlier_insights,
        ),
        quality=analysis.quality,
        ai_status=ai_status,
        ai=ai,
        methodology=ReportMethodology(),
    )
