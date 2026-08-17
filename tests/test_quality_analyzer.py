from datetime import date
from decimal import Decimal

from app.domain.insight_config import MIN_OUTLIER_SAMPLE_SIZE
from app.domain.models import InsightType, NormalizedSalesRow
from app.services.analyzer import analyze_rows
from app.services.insight_detector import detect_insights


def rows_from_prices(prices: list[str]) -> tuple[NormalizedSalesRow, ...]:
    return tuple(
        NormalizedSalesRow(
            row_number=index + 2,
            date=date(2026, 1, 1),
            product=f"P{index}",
            category="Office",
            region="North",
            quantity=1,
            unit_price=Decimal(price),
            discount=Decimal("0"),
            customer_type="Retail",
            sales=Decimal(price),
        )
        for index, price in enumerate(prices)
    )


def outliers(rows):
    return detect_insights(analyze_rows(rows), rows).outlier_insights


def test_normal_dataset_has_no_outlier_insight() -> None:
    assert outliers(rows_from_prices([str(value) for value in range(10, 18)])) == ()


def test_detects_high_and_low_potential_outliers_without_deleting_rows() -> None:
    high = rows_from_prices(["10", "11", "12", "13", "14", "15", "16", "100"])
    low = rows_from_prices(["0", "84", "85", "86", "87", "88", "89", "90"])

    high_insights = outliers(high)
    low_insights = outliers(low)
    assert {item.metric_name for item in high_insights} >= {"sales", "unit_price"}
    assert {item.metric_name for item in low_insights} >= {"sales", "unit_price"}
    assert all(item.type is InsightType.POTENTIAL_OUTLIER for item in high_insights)
    assert analyze_rows(high).kpis.transaction_count == len(high)


def test_small_sample_skips_outlier_detection() -> None:
    rows = rows_from_prices(["1"] * (MIN_OUTLIER_SAMPLE_SIZE - 1) + ["100"])

    assert outliers(rows) == ()


def test_zero_iqr_explicitly_skips_outlier_detection() -> None:
    rows = rows_from_prices(["10"] * 7 + ["100"])

    assert outliers(rows) == ()
