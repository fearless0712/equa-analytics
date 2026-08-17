from datetime import date
from decimal import Decimal

from app.domain.insight_config import MAX_BUSINESS_INSIGHTS
from app.domain.models import (
    DataQualityReport,
    InsightSeverity,
    InsightType,
    NormalizedSalesRow,
)
from app.services.analyzer import analyze_rows
from app.services.insight_detector import detect_insights


def sales_row(
    row_number: int,
    day: str,
    product: str,
    category: str,
    region: str,
    quantity: int,
    unit_price: str,
    customer_type: str | None = "Retail",
) -> NormalizedSalesRow:
    price = Decimal(unit_price)
    return NormalizedSalesRow(
        row_number=row_number,
        date=date.fromisoformat(day),
        product=product,
        category=category,
        region=region,
        quantity=quantity,
        unit_price=price,
        discount=Decimal("0"),
        customer_type=customer_type,
        sales=Decimal(quantity) * price,
    )


def collection(rows: tuple[NormalizedSalesRow, ...]):
    return detect_insights(analyze_rows(rows), rows)


def find_type(insights, insight_type: InsightType):
    return [item for item in insights if item.type is insight_type]


def test_detects_significant_monthly_growth_and_decline() -> None:
    growth_rows = (
        sales_row(2, "2026-01-01", "A", "Office", "North", 1, "100"),
        sales_row(3, "2026-02-01", "A", "Office", "North", 1, "200"),
    )
    decline_rows = (
        sales_row(2, "2026-01-01", "A", "Office", "North", 1, "200"),
        sales_row(3, "2026-02-01", "A", "Office", "North", 1, "100"),
    )

    growth = find_type(collection(growth_rows).business_insights, InsightType.SALES_GROWTH)[0]
    decline = find_type(collection(decline_rows).business_insights, InsightType.SALES_DECLINE)[0]
    assert growth.severity is InsightSeverity.POSITIVE
    assert growth.change_amount == 100
    assert decline.severity is InsightSeverity.WARNING
    assert decline.change_amount == -100


def test_small_monthly_change_is_not_significant() -> None:
    rows = (
        sales_row(2, "2026-01-01", "A", "Office", "North", 1, "100"),
        sales_row(3, "2026-02-01", "A", "Office", "North", 1, "110"),
    )
    insight = find_type(collection(rows).business_insights, InsightType.SALES_GROWTH)[0]

    assert insight.severity is InsightSeverity.INFO
    assert "significant=false" in insight.evidence


def test_unchanged_and_zero_base_percentage_are_not_guessed() -> None:
    unchanged = (
        sales_row(2, "2026-01-01", "A", "Office", "North", 1, "10"),
        sales_row(3, "2026-02-01", "A", "Office", "North", 1, "10"),
    )
    zero_base = (
        sales_row(2, "2026-01-01", "A", "Office", "North", 0, "10"),
        sales_row(3, "2026-02-01", "A", "Office", "North", 1, "10"),
    )

    assert find_type(collection(unchanged).business_insights, InsightType.SALES_STABLE)
    growth = find_type(collection(zero_base).business_insights, InsightType.SALES_GROWTH)[0]
    assert growth.change_pct is None
    assert "unavailable" in growth.summary


def test_imputed_month_is_not_classified_as_sales_decline() -> None:
    rows = (
        sales_row(2, "2026-01-01", "A", "Office", "North", 1, "100"),
        sales_row(3, "2026-03-01", "A", "Office", "North", 1, "50"),
    )
    insights = collection(rows)

    assert not find_type(insights.business_insights, InsightType.SALES_DECLINE)
    assert find_type(insights.business_insights, InsightType.INSUFFICIENT_DATA)
    assert find_type(insights.quality_insights, InsightType.DATA_GAP)


def test_detects_top_one_and_top_three_concentration_for_each_dimension() -> None:
    rows = (
        sales_row(2, "2026-01-01", "A", "C1", "R1", 6, "10"),
        sales_row(3, "2026-01-01", "B", "C2", "R2", 2, "10"),
        sales_row(4, "2026-01-01", "C", "C3", "R3", 1, "10"),
        sales_row(5, "2026-01-01", "D", "C4", "R4", 1, "10"),
    )
    insights = find_type(collection(rows).business_insights, InsightType.CONCENTRATION)

    assert {item.dimension for item in insights} == {"product", "category", "region"}
    assert all(item.severity is InsightSeverity.WARNING for item in insights)
    assert all("top_one_share=60.0" in item.evidence for item in insights)
    assert all("top_three_share=90.0" in item.evidence for item in insights)


def test_limited_diversity_and_zero_total_do_not_claim_concentration_risk() -> None:
    limited = (
        sales_row(2, "2026-01-01", "A", "Office", "North", 1, "10"),
    )
    zero_total = tuple(
        sales_row(index + 2, "2026-01-01", name, f"C{name}", f"R{name}", 0, "10")
        for index, name in enumerate(("A", "B", "C", "D"))
    )

    assert find_type(collection(limited).business_insights, InsightType.INSUFFICIENT_DATA)
    concentration = find_type(
        collection(zero_total).business_insights, InsightType.CONCENTRATION
    )
    assert all(item.severity is InsightSeverity.INFO for item in concentration)


def test_zero_activity_distinguishes_source_rows_products_and_imputed_months() -> None:
    rows = (
        sales_row(2, "2026-01-01", "Zero Product", "Office", "North", 0, "10"),
        sales_row(3, "2026-03-01", "Active", "Office", "North", 1, "10"),
    )
    insights = collection(rows)
    zero = find_type(insights.business_insights, InsightType.ZERO_ACTIVITY)

    assert any(item.period == "2026-01" and item.metric_name == "sales" for item in zero)
    assert any(item.dimension_value == "Zero Product" for item in zero)
    assert not any(item.period == "2026-02" for item in zero)


def test_category_growth_decline_stable_and_unavailable() -> None:
    moving = (
        sales_row(2, "2026-01-01", "A", "Up", "North", 1, "10"),
        sales_row(3, "2026-01-01", "B", "Down", "North", 1, "30"),
        sales_row(4, "2026-02-01", "A", "Up", "North", 1, "20"),
        sales_row(5, "2026-02-01", "B", "Down", "North", 1, "10"),
    )
    stable = (
        sales_row(2, "2026-01-01", "A", "Same", "North", 1, "10"),
        sales_row(3, "2026-02-01", "A", "Same", "North", 1, "10"),
    )
    single = (sales_row(2, "2026-01-01", "A", "Only", "North", 1, "10"),)

    moving_insights = collection(moving).business_insights
    assert find_type(moving_insights, InsightType.CATEGORY_GROWTH)
    assert find_type(moving_insights, InsightType.CATEGORY_DECLINE)
    assert find_type(collection(stable).business_insights, InsightType.CATEGORY_STABLE)
    unavailable = find_type(
        collection(single).business_insights, InsightType.INSUFFICIENT_DATA
    )
    assert any(item.dimension == "category" for item in unavailable)


def test_quality_insights_cover_invalid_duplicates_optional_and_gaps() -> None:
    duplicate = sales_row(2, "2026-01-01", "A", "Office", "North", 1, "10", None)
    repeated = duplicate.model_copy(update={"row_number": 3})
    march = sales_row(4, "2026-03-01", "B", "Home", "South", 1, "10", None)
    rows = (duplicate, repeated, march)
    analysis = analyze_rows(rows, total_rows=4, invalid_rows=1)
    insights = detect_insights(analysis, rows).quality_insights

    assert {item.id for item in insights} >= {
        "quality-invalid-rows",
        "quality-duplicate-rows",
        "quality-missing-optional",
        "quality-imputed-months",
    }


def test_metadata_covers_date_range_year_crossing_and_month_counts() -> None:
    rows = (
        sales_row(2, "2025-12-15", "A", "Office", "North", 1, "10"),
        sales_row(3, "2026-02-02", "B", "Home", "South", 1, "10"),
    )
    metadata = collection(rows).metadata

    assert metadata.date_from == date(2025, 12, 15)
    assert metadata.date_to == date(2026, 2, 2)
    assert metadata.observed_months == 2
    assert metadata.imputed_months == 1
    assert metadata.row_count == 2
    assert metadata.product_count == 2
    assert metadata.potential_outliers == 0


def test_order_is_deterministic_and_business_limit_is_enforced() -> None:
    rows = tuple(
        sales_row(index + 2, "2026-01-01", f"P{index:02}", "Office", "North", 0, "10")
        for index in range(30)
    )
    first = collection(rows).business_insights
    second = collection(rows).business_insights

    assert len(first) == MAX_BUSINESS_INSIGHTS
    assert [item.id for item in first] == [item.id for item in second]
    assert [item.id for item in first] == list(dict.fromkeys(item.id for item in first))


def test_quality_override_can_represent_invalid_rows_without_recalculation() -> None:
    rows = (sales_row(2, "2026-01-01", "A", "Office", "North", 1, "10"),)
    analysis = analyze_rows(rows)
    quality = DataQualityReport(
        total_rows=2,
        valid_rows=1,
        invalid_rows=1,
        duplicate_rows=0,
        missing_optional_values=0,
    )
    altered = analysis.model_copy(update={"quality": quality})

    assert any(
        item.id == "quality-invalid-rows"
        for item in detect_insights(altered, rows).quality_insights
    )
