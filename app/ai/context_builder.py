import json
from decimal import Decimal

from app.ai.models import AiContextPayload
from app.domain.models import AnalysisResult, BusinessInsight, DimensionMetric, InsightCollection

LATEST_MONTHS_LIMIT = 6
DIMENSION_LIMIT = 5
BUSINESS_INSIGHT_LIMIT = 10
QUALITY_INSIGHT_LIMIT = 5
OUTLIER_INSIGHT_LIMIT = 3
MAX_CONTEXT_CHARACTERS = 12_000
MAX_DATA_STRING_LENGTH = 240


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _text(value: str | None) -> str | None:
    return value[:MAX_DATA_STRING_LENGTH] if value is not None else None


def _dimension(item: DimensionMetric) -> dict[str, object]:
    return {
        "name": _text(item.name),
        "sales": _decimal(item.sales),
        "quantity": item.quantity,
        "sales_share": _decimal(item.sales_share),
    }


def _insight(item: BusinessInsight) -> dict[str, object]:
    return {
        "type": item.type.value,
        "severity": item.severity.value,
        "title": _text(item.title),
        "summary": _text(item.summary),
        "metric_name": item.metric_name,
        "current_value": _decimal(item.current_value) if isinstance(item.current_value, Decimal) else item.current_value,
        "previous_value": _decimal(item.previous_value) if isinstance(item.previous_value, Decimal) else item.previous_value,
        "change_amount": _decimal(item.change_amount) if isinstance(item.change_amount, Decimal) else item.change_amount,
        "change_pct": _decimal(item.change_pct),
        "dimension": item.dimension,
        "dimension_value": _text(item.dimension_value),
        "period": item.period,
    }


def serialize_ai_context(payload: AiContextPayload) -> str:
    return json.dumps(payload.model_dump(mode="json"), ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def build_ai_context(analysis: AnalysisResult, insights: InsightCollection) -> AiContextPayload:
    monthly = tuple(
        {
            "year_month": item.year_month,
            "sales": _decimal(item.sales),
            "quantity": item.quantity,
            "sales_change": _decimal(item.sales_change),
            "sales_change_pct": _decimal(item.sales_change_pct),
            "is_imputed": item.is_imputed,
        }
        for item in analysis.monthly[-LATEST_MONTHS_LIMIT:]
    )
    payload = AiContextPayload(
        metadata={
            "date_from": insights.metadata.date_from.isoformat() if insights.metadata.date_from else None,
            "date_to": insights.metadata.date_to.isoformat() if insights.metadata.date_to else None,
            "observed_months": insights.metadata.observed_months,
            "imputed_months": insights.metadata.imputed_months,
            "row_count": insights.metadata.row_count,
            "product_count": insights.metadata.product_count,
            "category_count": insights.metadata.category_count,
            "region_count": insights.metadata.region_count,
            "potential_outlier_count": insights.metadata.potential_outliers,
        },
        kpis={
            "total_sales": _decimal(analysis.kpis.total_sales),
            "total_quantity": analysis.kpis.total_quantity,
            "transaction_count": analysis.kpis.transaction_count,
            "average_order_value": _decimal(analysis.kpis.average_order_value),
            "average_unit_price": _decimal(analysis.kpis.average_unit_price),
            "unique_products": analysis.kpis.unique_products,
            "unique_categories": analysis.kpis.unique_categories,
            "unique_regions": analysis.kpis.unique_regions,
        },
        monthly=monthly,
        dimensions={
            "products": tuple(_dimension(item) for item in analysis.top_products[:DIMENSION_LIMIT]),
            "categories": tuple(_dimension(item) for item in analysis.categories[:DIMENSION_LIMIT]),
            "regions": tuple(_dimension(item) for item in analysis.regions[:DIMENSION_LIMIT]),
        },
        detected_insights={
            "business": tuple(_insight(item) for item in insights.business_insights[:BUSINESS_INSIGHT_LIMIT]),
            "quality": tuple(_insight(item) for item in insights.quality_insights[:QUALITY_INSIGHT_LIMIT]),
            "outliers": tuple(_insight(item) for item in insights.outlier_insights[:OUTLIER_INSIGHT_LIMIT]),
        },
    )
    if len(serialize_ai_context(payload)) <= MAX_CONTEXT_CHARACTERS:
        return payload

    # Deterministically discard lower-priority collections; raw data is never a fallback.
    data = payload.model_dump()
    for group in ("outliers", "quality", "business"):
        while data["detected_insights"][group] and len(serialize_ai_context(AiContextPayload.model_validate(data))) > MAX_CONTEXT_CHARACTERS:
            data["detected_insights"][group] = data["detected_insights"][group][:-1]
    for group in ("regions", "categories", "products"):
        while data["dimensions"][group] and len(serialize_ai_context(AiContextPayload.model_validate(data))) > MAX_CONTEXT_CHARACTERS:
            data["dimensions"][group] = data["dimensions"][group][:-1]
    while data["monthly"] and len(serialize_ai_context(AiContextPayload.model_validate(data))) > MAX_CONTEXT_CHARACTERS:
        data["monthly"] = data["monthly"][1:]
    bounded = AiContextPayload.model_validate(data)
    if len(serialize_ai_context(bounded)) > MAX_CONTEXT_CHARACTERS:
        raise ValueError("AI context exceeds the configured safe limit")
    return bounded
