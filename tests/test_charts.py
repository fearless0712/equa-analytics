import base64
import json
from datetime import date
from decimal import Decimal

from app.domain.models import KpiSummary, NormalizedSalesRow
from app.presentation.charts import build_dashboard_charts
from app.services.analyzer import analyze_rows


def row(
    row_number: int,
    day: str,
    product: str = "Product A",
    category: str = "Office",
    region: str = "North",
) -> NormalizedSalesRow:
    return NormalizedSalesRow(
        row_number=row_number,
        date=date.fromisoformat(day),
        product=product,
        category=category,
        region=region,
        quantity=2,
        unit_price=Decimal("10.5"),
        discount=Decimal("0"),
        customer_type=None,
        sales=Decimal("21.0"),
    )


def decode(payload: str) -> dict:
    return json.loads(base64.b64decode(payload).decode("utf-8"))


def test_builds_all_required_chart_specs_from_analysis_result() -> None:
    analysis = analyze_rows(
        (
            row(2, "2026-01-02"),
            row(3, "2026-03-02", "Product B", "Home", "South"),
        )
    )
    charts = build_dashboard_charts(analysis)

    assert decode(charts.monthly_sales.payload)["data"][0]["y"] == [21.0, 0.0, 21.0]
    assert decode(charts.monthly_quantity.payload)["data"][0]["y"] == [2, 0, 2]
    assert decode(charts.top_products.payload)["data"][0]["orientation"] == "h"
    assert decode(charts.categories.payload)["data"][0]["y"] == ["Home", "Office"]
    assert decode(charts.regions.payload)["data"][0]["y"] == ["North", "South"]
    assert "No source rows / imputed zero" in decode(
        charts.monthly_sales.payload
    )["data"][0]["customdata"]


def test_charts_use_analysis_metrics_without_recalculating_kpis() -> None:
    analysis = analyze_rows((row(2, "2026-01-02"),))
    unrelated_kpis = KpiSummary(
        total_sales=Decimal("999999"),
        total_quantity=999,
        transaction_count=999,
        average_order_value=Decimal("1"),
        average_unit_price=Decimal("1"),
        unique_products=99,
        unique_categories=99,
        unique_regions=99,
    )
    altered = analysis.model_copy(update={"kpis": unrelated_kpis})

    assert decode(build_dashboard_charts(altered).monthly_sales.payload)["data"][0][
        "y"
    ] == [21.0]


def test_empty_and_small_analysis_create_valid_specs() -> None:
    empty = build_dashboard_charts(analyze_rows(()))
    small = build_dashboard_charts(analyze_rows((row(2, "2026-01-02"),)))

    assert decode(empty.monthly_sales.payload)["data"][0]["x"] == []
    assert decode(empty.top_products.payload)["data"][0]["y"] == []
    assert decode(small.top_products.payload)["data"][0]["y"] == ["Product A"]
