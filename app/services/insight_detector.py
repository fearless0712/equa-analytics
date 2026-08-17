import hashlib
from decimal import Decimal

from app.domain.insight_config import (
    MAX_BUSINESS_INSIGHTS,
    MAX_OUTLIER_INSIGHTS,
    MAX_QUALITY_INSIGHTS,
    MIN_CONCENTRATION_DIMENSIONS,
    SIGNIFICANT_ABSOLUTE_SHARE_PCT,
    SIGNIFICANT_CHANGE_PCT,
    TOP_ONE_CONCENTRATION_PCT,
    TOP_THREE_CONCENTRATION_PCT,
)
from app.domain.models import (
    AnalysisResult,
    BusinessInsight,
    DimensionMetric,
    InsightCollection,
    InsightSeverity,
    InsightType,
    NormalizedSalesRow,
)
from app.services.kpi_calculator import decimal_percentage
from app.services.quality_analyzer import (
    build_analysis_metadata,
    detect_outlier_insights,
    detect_quality_insights,
)

SEVERITY_ORDER = {
    InsightSeverity.CRITICAL: 0,
    InsightSeverity.WARNING: 1,
    InsightSeverity.POSITIVE: 2,
    InsightSeverity.INFO: 3,
}


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{digest}"


def _sort_insights(
    insights: list[BusinessInsight], limit: int
) -> tuple[BusinessInsight, ...]:
    return tuple(
        sorted(
            insights,
            key=lambda item: (
                SEVERITY_ORDER[item.severity],
                item.type.value,
                item.period or "",
                item.dimension or "",
                item.dimension_value or "",
                item.id,
            ),
        )[:limit]
    )


def _is_significant(
    analysis: AnalysisResult, change: Decimal, change_pct: Decimal | None
) -> bool:
    if change_pct is None or analysis.kpis.total_sales == 0:
        return False
    absolute_share = decimal_percentage(abs(change), analysis.kpis.total_sales)
    return bool(
        abs(change_pct) >= SIGNIFICANT_CHANGE_PCT
        and absolute_share is not None
        and absolute_share >= SIGNIFICANT_ABSOLUTE_SHARE_PCT
    )


def _monthly_change_insights(analysis: AnalysisResult) -> list[BusinessInsight]:
    real_indexes = [
        index for index, metric in enumerate(analysis.monthly) if not metric.is_imputed
    ]
    if not real_indexes:
        return []
    current_index = real_indexes[-1]
    current = analysis.monthly[current_index]
    if current_index == 0 or analysis.monthly[current_index - 1].is_imputed:
        return [
            BusinessInsight(
                id=f"monthly-insufficient-{current.year_month}",
                type=InsightType.INSUFFICIENT_DATA,
                severity=InsightSeverity.INFO,
                title="Monthly comparison unavailable",
                summary=f"Sales for {current.year_month} cannot be compared with a preceding source month.",
                metric_name="sales",
                current_value=current.sales,
                period=current.year_month,
            )
        ]

    previous = analysis.monthly[current_index - 1]
    change = current.sales_change
    if change is None:
        return []
    if change > 0:
        significant = _is_significant(analysis, change, current.sales_change_pct)
        insight_type = InsightType.SALES_GROWTH
        severity = InsightSeverity.POSITIVE if significant else InsightSeverity.INFO
        title = "Significant monthly sales growth" if significant else "Monthly sales increased"
    elif change < 0:
        significant = _is_significant(analysis, change, current.sales_change_pct)
        insight_type = InsightType.SALES_DECLINE
        severity = InsightSeverity.WARNING if significant else InsightSeverity.INFO
        title = "Significant monthly sales decline" if significant else "Monthly sales decreased"
    else:
        significant = False
        insight_type = InsightType.SALES_STABLE
        severity = InsightSeverity.INFO
        title = "Monthly sales were unchanged"

    direction = "changed"
    if change > 0:
        direction = "increased"
    elif change < 0:
        direction = "decreased"
    pct_text = (
        " Percentage change is unavailable because the comparison base is zero."
        if current.sales_change_pct is None
        else f" The change was {current.sales_change_pct}%."
    )
    return [
        BusinessInsight(
            id=f"monthly-sales-{current.year_month}",
            type=insight_type,
            severity=severity,
            title=title,
            summary=f"Sales {direction} from {previous.year_month} to {current.year_month}.{pct_text}",
            metric_name="sales",
            current_value=current.sales,
            previous_value=previous.sales,
            change_amount=change,
            change_pct=current.sales_change_pct,
            period=current.year_month,
            evidence=(
                f"significant_change_pct={SIGNIFICANT_CHANGE_PCT}",
                f"minimum_total_sales_share_pct={SIGNIFICANT_ABSOLUTE_SHARE_PCT}",
                f"significant={str(significant).lower()}",
            ),
        )
    ]


def _concentration_insight(
    analysis: AnalysisResult,
    dimension: str,
    metrics: tuple[DimensionMetric, ...],
) -> BusinessInsight:
    if len(metrics) < MIN_CONCENTRATION_DIMENSIONS:
        return BusinessInsight(
            id=f"concentration-{dimension}-limited",
            type=InsightType.INSUFFICIENT_DATA,
            severity=InsightSeverity.INFO,
            title=f"Limited {dimension} diversity",
            summary=f"Only {len(metrics)} {dimension} values are available, so concentration risk is not classified.",
            metric_name="dimension_count",
            current_value=len(metrics),
            dimension=dimension,
        )

    total_sales = analysis.kpis.total_sales
    top_one_share = metrics[0].sales_share
    top_three_sales = sum(
        (item.sales for item in metrics[:3]), start=Decimal("0")
    )
    top_three_share = decimal_percentage(top_three_sales, total_sales)
    concentrated = bool(
        total_sales > 0
        and (
            (top_one_share is not None and top_one_share >= TOP_ONE_CONCENTRATION_PCT)
            or (
                top_three_share is not None
                and top_three_share >= TOP_THREE_CONCENTRATION_PCT
            )
        )
    )
    return BusinessInsight(
        id=f"concentration-{dimension}",
        type=InsightType.CONCENTRATION,
        severity=(InsightSeverity.WARNING if concentrated else InsightSeverity.INFO),
        title=(
            f"High sales concentration by {dimension}"
            if concentrated
            else f"Sales concentration by {dimension} is below thresholds"
        ),
        summary=f"The leading {dimension} represents {top_one_share if top_one_share is not None else 'N/A'}% of sales; the top three represent {top_three_share if top_three_share is not None else 'N/A'}%.",
        metric_name="sales_share",
        current_value=top_one_share,
        dimension=dimension,
        dimension_value=metrics[0].name,
        evidence=(
            f"top_one_share={top_one_share}",
            f"top_three_share={top_three_share}",
        ),
    )


def _zero_activity_insights(analysis: AnalysisResult) -> list[BusinessInsight]:
    insights: list[BusinessInsight] = []
    for metric in analysis.monthly:
        if metric.is_imputed:
            continue
        if metric.sales == 0:
            insights.append(
                BusinessInsight(
                    id=f"zero-month-sales-{metric.year_month}",
                    type=InsightType.ZERO_ACTIVITY,
                    severity=InsightSeverity.WARNING,
                    title="Source month has zero sales",
                    summary=f"Source rows exist for {metric.year_month}, but calculated sales are zero.",
                    metric_name="sales",
                    current_value=metric.sales,
                    period=metric.year_month,
                )
            )
        if metric.quantity == 0:
            insights.append(
                BusinessInsight(
                    id=f"zero-month-quantity-{metric.year_month}",
                    type=InsightType.ZERO_ACTIVITY,
                    severity=InsightSeverity.WARNING,
                    title="Source month has zero quantity",
                    summary=f"Source rows exist for {metric.year_month}, but total quantity is zero.",
                    metric_name="quantity",
                    current_value=metric.quantity,
                    period=metric.year_month,
                )
            )
    for product in analysis.products:
        if product.sales == 0:
            insights.append(
                BusinessInsight(
                    id=_stable_id("zero-product-sales", product.name),
                    type=InsightType.ZERO_ACTIVITY,
                    severity=InsightSeverity.INFO,
                    title="Product has zero sales",
                    summary=f"The product {product.name} has source rows but calculated sales are zero.",
                    metric_name="sales",
                    current_value=product.sales,
                    dimension="product",
                    dimension_value=product.name,
                )
            )
        if product.quantity == 0:
            insights.append(
                BusinessInsight(
                    id=_stable_id("zero-product-quantity", product.name),
                    type=InsightType.ZERO_ACTIVITY,
                    severity=InsightSeverity.INFO,
                    title="Product has zero quantity",
                    summary=f"The product {product.name} has source rows but total quantity is zero.",
                    metric_name="quantity",
                    current_value=product.quantity,
                    dimension="product",
                    dimension_value=product.name,
                )
            )
    return insights


def _category_movement_insights(analysis: AnalysisResult) -> list[BusinessInsight]:
    growth = analysis.largest_category_growth
    decline = analysis.largest_category_decline
    if growth is None or decline is None:
        return [
            BusinessInsight(
                id="category-movement-insufficient",
                type=InsightType.INSUFFICIENT_DATA,
                severity=InsightSeverity.INFO,
                title="Category movement comparison unavailable",
                summary="Category movement requires comparable categories in two source months.",
                dimension="category",
            )
        ]

    insights: list[BusinessInsight] = []
    if growth.change_amount > 0:
        insights.append(
            BusinessInsight(
                id=_stable_id("category-growth", growth.name),
                type=InsightType.CATEGORY_GROWTH,
                severity=InsightSeverity.POSITIVE,
                title="Largest category increase",
                summary=f"The category {growth.name} had the largest sales increase between {growth.previous_month} and {growth.current_month}.",
                metric_name="sales",
                current_value=growth.current_sales,
                previous_value=growth.previous_sales,
                change_amount=growth.change_amount,
                change_pct=growth.change_pct,
                dimension="category",
                dimension_value=growth.name,
                period=growth.current_month,
            )
        )
    if decline.change_amount < 0:
        insights.append(
            BusinessInsight(
                id=_stable_id("category-decline", decline.name),
                type=InsightType.CATEGORY_DECLINE,
                severity=InsightSeverity.WARNING,
                title="Largest category decrease",
                summary=f"The category {decline.name} had the largest sales decrease between {decline.previous_month} and {decline.current_month}.",
                metric_name="sales",
                current_value=decline.current_sales,
                previous_value=decline.previous_sales,
                change_amount=decline.change_amount,
                change_pct=decline.change_pct,
                dimension="category",
                dimension_value=decline.name,
                period=decline.current_month,
            )
        )
    if not insights:
        insights.append(
            BusinessInsight(
                id="category-movement-stable",
                type=InsightType.CATEGORY_STABLE,
                severity=InsightSeverity.INFO,
                title="Comparable category sales were unchanged",
                summary="The largest and smallest comparable category changes were both zero.",
                metric_name="sales",
                change_amount=Decimal("0"),
                dimension="category",
                period=growth.current_month,
            )
        )
    return insights


def detect_insights(
    analysis: AnalysisResult, rows: tuple[NormalizedSalesRow, ...]
) -> InsightCollection:
    metadata = build_analysis_metadata(analysis, rows)
    business = _monthly_change_insights(analysis)
    business.extend(
        _concentration_insight(analysis, dimension, metrics)
        for dimension, metrics in (
            ("product", analysis.products),
            ("category", analysis.categories),
            ("region", analysis.regions),
        )
    )
    business.extend(_zero_activity_insights(analysis))
    business.extend(_category_movement_insights(analysis))
    outliers = list(detect_outlier_insights(rows))
    metadata = metadata.model_copy(
        update={
            "potential_outliers": sum(
                int(insight.current_value or 0) for insight in outliers
            )
        }
    )
    quality = list(detect_quality_insights(analysis, metadata))
    return InsightCollection(
        business_insights=_sort_insights(business, MAX_BUSINESS_INSIGHTS),
        quality_insights=_sort_insights(quality, MAX_QUALITY_INSIGHTS),
        outlier_insights=_sort_insights(outliers, MAX_OUTLIER_INSIGHTS),
        metadata=metadata,
    )
