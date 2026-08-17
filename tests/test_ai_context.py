import json
from decimal import Decimal
from pathlib import Path

from app.ai.context_builder import (
    BUSINESS_INSIGHT_LIMIT,
    DIMENSION_LIMIT,
    LATEST_MONTHS_LIMIT,
    MAX_CONTEXT_CHARACTERS,
    build_ai_context,
    serialize_ai_context,
)
from app.services.analyzer import analyze_rows
from app.services.csv_reader import read_csv_bytes
from app.services.insight_detector import detect_insights
from app.services.normalizer import normalize_csv_result


def _results():
    read = read_csv_bytes(
        Path("sample_data/valid_sales.csv").read_bytes(),
        max_file_size=5 * 1024 * 1024,
        max_rows=10_000,
    )
    normalized = normalize_csv_result(read)
    analysis = analyze_rows(normalized.valid_rows, total_rows=normalized.total_rows, invalid_rows=0)
    return analysis, detect_insights(analysis, normalized.valid_rows)


def test_context_is_bounded_deterministic_and_contains_only_aggregates() -> None:
    analysis, insights = _results()
    first = build_ai_context(analysis, insights)
    second = build_ai_context(analysis, insights)
    serialized = serialize_ai_context(first)

    assert first == second
    assert len(first.monthly) <= LATEST_MONTHS_LIMIT
    assert all(len(items) <= DIMENSION_LIMIT for items in first.dimensions.values())
    assert len(first.detected_insights["business"]) <= BUSINESS_INSIGHT_LIMIT
    assert len(serialized) <= MAX_CONTEXT_CHARACTERS
    for forbidden in ("raw_rows", "filename", "customer_type", "csrf", "secret_key", "chart"):
        assert forbidden not in serialized.lower()


def test_context_serializes_decimal_as_exact_string_and_none_as_null() -> None:
    analysis, insights = _results()
    analysis = analysis.model_copy(
        update={"kpis": analysis.kpis.model_copy(update={"total_sales": Decimal("1234.50"), "average_order_value": None})}
    )
    data = json.loads(serialize_ai_context(build_ai_context(analysis, insights)))
    assert data["kpis"]["total_sales"] == "1234.50"
    assert data["kpis"]["average_order_value"] is None


def test_context_prunes_low_priority_data_to_enforce_hard_size_limit() -> None:
    analysis, insights = _results()
    long_text = "untrusted-dimension-value-" * 30
    dimension = analysis.products[0].model_copy(update={"name": long_text})
    analysis = analysis.model_copy(
        update={
            "top_products": (dimension,) * 5,
            "categories": (dimension,) * 5,
            "regions": (dimension,) * 5,
        }
    )
    source = insights.business_insights[0]
    oversized = tuple(
        source.model_copy(
            update={
                "id": f"oversized-{index}",
                "title": long_text,
                "summary": long_text,
                "dimension_value": long_text,
            }
        )
        for index in range(10)
    )
    insights = insights.model_copy(
        update={
            "business_insights": oversized,
            "quality_insights": oversized[:5],
            "outlier_insights": oversized[:3],
        }
    )

    context = build_ai_context(analysis, insights)

    assert len(serialize_ai_context(context)) <= MAX_CONTEXT_CHARACTERS
    assert len(context.detected_insights["outliers"]) < 3
