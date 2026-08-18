from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.ai.fake_ai import FakeAiProvider
from app.ai.context_builder import build_ai_context
from app.domain.report_models import BusinessReport, ReportAiStatus, ReportTrend
from app.services.report_builder import (
    REPORT_DIMENSION_LIMIT,
    REPORT_MONTH_LIMIT,
    build_business_report,
)
from tests.test_ai_context import _results

GENERATED_AT = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)


def test_builder_creates_deterministic_report_without_ai() -> None:
    analysis, insights = _results()

    first = build_business_report(
        analysis, insights, generated_at=GENERATED_AT
    )
    second = build_business_report(
        analysis, insights, generated_at=GENERATED_AT
    )

    assert first == second
    assert first.schema_version == "1.0"
    assert first.ai_status is ReportAiStatus.NOT_REQUESTED
    assert first.ai is None
    assert first.executive_summary.total_sales == analysis.kpis.total_sales
    assert isinstance(first.executive_summary.total_sales, Decimal)
    assert first.executive_summary.latest_trend in set(ReportTrend)
    assert first.metadata.generated_at == GENERATED_AT
    assert first.metadata.total_rows == analysis.quality.total_rows
    assert first.metadata.analyzed_rows == insights.metadata.row_count
    assert first.metadata.potential_outliers == insights.metadata.potential_outliers
    assert first.metadata.date_from == insights.metadata.date_from


def test_builder_includes_existing_ai_response_without_generating_it() -> None:
    analysis, insights = _results()
    context = build_ai_context(analysis, insights)
    ai = FakeAiProvider().generate(context)

    report = build_business_report(
        analysis,
        insights,
        ai=ai,
        generated_at=GENERATED_AT,
    )

    assert report.ai_status is ReportAiStatus.INCLUDED
    assert report.ai is ai
    assert report.ai.recommendations


def test_builder_marks_ai_unavailable_without_blocking_report() -> None:
    analysis, insights = _results()

    report = build_business_report(
        analysis,
        insights,
        ai_unavailable=True,
        generated_at=GENERATED_AT,
    )

    assert report.ai_status is ReportAiStatus.UNAVAILABLE
    assert report.ai is None
    assert report.kpis == analysis.kpis
    assert report.insights.business == insights.business_insights


def test_report_applies_content_limits_without_mutating_analysis() -> None:
    analysis, insights = _results()
    monthly = analysis.monthly * (REPORT_MONTH_LIMIT + 1)
    dimensions = analysis.products * (REPORT_DIMENSION_LIMIT + 1)
    expanded = analysis.model_copy(
        update={
            "monthly": monthly,
            "products": dimensions,
            "categories": dimensions,
            "regions": dimensions,
        }
    )

    report = build_business_report(
        expanded, insights, generated_at=GENERATED_AT
    )

    assert len(report.monthly) == REPORT_MONTH_LIMIT
    assert len(report.top_products) == REPORT_DIMENSION_LIMIT
    assert len(report.top_categories) == REPORT_DIMENSION_LIMIT
    assert len(report.top_regions) == REPORT_DIMENSION_LIMIT
    assert len(expanded.monthly) > len(report.monthly)


def test_methodology_matches_current_analysis_contract() -> None:
    analysis, insights = _results()
    report = build_business_report(
        analysis, insights, generated_at=GENERATED_AT
    )

    assert report.metadata.currency is None
    assert report.methodology.sales_formula == "quantity * unit_price * (1 - discount)"
    assert "presentation-only" in report.methodology.decimal_note
    assert "retained" in report.methodology.duplicate_note
    assert "not removed" in report.methodology.outlier_note
    assert "does not calculate KPIs" in report.methodology.ai_note


def test_report_serialization_excludes_raw_and_secret_fields() -> None:
    analysis, insights = _results()
    report = build_business_report(
        analysis, insights, generated_at=GENERATED_AT
    )
    serialized = report.model_dump_json().lower()

    for forbidden in (
        "raw_rows",
        "customer_type",
        "filename",
        "openai_api_key",
        "secret_key",
        "plotly",
        "csrf",
    ):
        assert forbidden not in serialized


def test_report_model_rejects_inconsistent_ai_state_and_naive_timestamp() -> None:
    analysis, insights = _results()
    report = build_business_report(
        analysis, insights, generated_at=GENERATED_AT
    )
    with pytest.raises(ValidationError, match="included AI status"):
        BusinessReport.model_validate(
            {
                **report.model_dump(),
                "ai_status": "included",
                "ai": None,
            }
        )
    with pytest.raises(ValidationError, match="timezone-aware"):
        build_business_report(
            analysis,
            insights,
            generated_at=datetime(2026, 8, 18, 12, 0),
        )
    context = build_ai_context(analysis, insights)
    with pytest.raises(ValueError, match="mutually exclusive"):
        build_business_report(
            analysis,
            insights,
            ai=FakeAiProvider().generate(context),
            ai_unavailable=True,
            generated_at=GENERATED_AT,
        )
