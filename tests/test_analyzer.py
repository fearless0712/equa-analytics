from datetime import date
from decimal import Decimal

from app.domain.models import NormalizedSalesRow
from app.services.analyzer import ANALYSIS_COLUMNS, analyze_rows, rows_to_dataframe


def sales_row(
    row_number: int,
    day: str,
    product: str,
    category: str,
    region: str,
    quantity: int,
    unit_price: str,
    discount: str = "0",
    customer_type: str | None = "Retail",
) -> NormalizedSalesRow:
    price = Decimal(unit_price)
    rate = Decimal(discount)
    sales = Decimal(quantity) * price * (Decimal("1") - rate)
    return NormalizedSalesRow(
        row_number=row_number,
        date=date.fromisoformat(day),
        product=product,
        category=category,
        region=region,
        quantity=quantity,
        unit_price=price,
        discount=rate,
        customer_type=customer_type,
        sales=sales,
    )


def test_dataframe_contains_only_analysis_columns_and_decimal_money() -> None:
    frame = rows_to_dataframe(
        (sales_row(2, "2026-01-01", "A", "Office", "North", 1, "1.1"),)
    )

    assert tuple(frame.columns) == ANALYSIS_COLUMNS
    assert isinstance(frame.at[0, "sales"], Decimal)
    assert isinstance(frame.at[0, "unit_price"], Decimal)
    assert "gross_profit" not in frame.columns


def test_kpis_match_hand_calculation_without_float_error() -> None:
    rows = (
        sales_row(2, "2026-01-01", "A", "Office", "North", 1, "1.1"),
        sales_row(3, "2026-01-02", "B", "Home", "South", 2, "1.1"),
    )
    kpis = analyze_rows(rows).kpis

    assert kpis.total_sales == Decimal("3.3")
    assert kpis.total_quantity == 3
    assert kpis.transaction_count == 2
    assert kpis.average_order_value == Decimal("1.65")
    assert kpis.average_unit_price == Decimal("1.1")
    assert kpis.unique_products == 2
    assert kpis.unique_categories == 2
    assert kpis.unique_regions == 2


def test_zero_quantity_makes_average_unit_price_unavailable() -> None:
    rows = (sales_row(2, "2026-01-01", "A", "Office", "North", 0, "10"),)
    kpis = analyze_rows(rows).kpis

    assert kpis.total_sales == 0
    assert kpis.average_order_value == 0
    assert kpis.average_unit_price is None


def test_empty_analysis_has_zero_kpis_and_no_metrics() -> None:
    result = analyze_rows(())

    assert result.kpis.total_sales == 0
    assert result.kpis.transaction_count == 0
    assert result.kpis.average_order_value is None
    assert result.monthly == ()
    assert result.products == ()


def test_monthly_metrics_changes_and_first_month_none() -> None:
    rows = (
        sales_row(2, "2026-01-01", "A", "Office", "North", 2, "10"),
        sales_row(3, "2026-02-01", "A", "Office", "North", 3, "10"),
    )
    monthly = analyze_rows(rows).monthly

    assert monthly[0].sales_change is None
    assert monthly[0].sales_change_pct is None
    assert monthly[1].sales == Decimal("30")
    assert monthly[1].sales_change == Decimal("10")
    assert monthly[1].sales_change_pct == Decimal("50.0")
    assert monthly[1].quantity_change == 1
    assert monthly[1].quantity_change_pct == Decimal("50.0")


def test_monthly_metrics_fill_missing_month_and_handle_previous_zero() -> None:
    rows = (
        sales_row(2, "2025-12-01", "A", "Office", "North", 1, "10"),
        sales_row(3, "2026-02-01", "A", "Office", "North", 2, "10"),
    )
    monthly = analyze_rows(rows).monthly

    assert [metric.year_month for metric in monthly] == [
        "2025-12",
        "2026-01",
        "2026-02",
    ]
    assert monthly[1].is_imputed is True
    assert monthly[1].sales == 0
    assert monthly[1].transaction_count == 0
    assert monthly[2].sales_change == 20
    assert monthly[2].sales_change_pct is None
    assert monthly[2].quantity_change_pct is None


def test_dimensions_use_stable_sales_desc_name_asc_ranking() -> None:
    rows = (
        sales_row(2, "2026-01-01", "Beta", "Office", "West", 1, "10"),
        sales_row(3, "2026-01-02", "Alpha", "Office", "East", 2, "5"),
        sales_row(4, "2026-01-03", "Gamma", "Home", "North", 1, "5"),
    )
    result = analyze_rows(rows)

    assert [(item.name, item.rank) for item in result.products] == [
        ("Alpha", 1),
        ("Beta", 2),
        ("Gamma", 3),
    ]
    assert result.products[0].sales_share == Decimal("40.0")
    assert result.categories[0].name == "Office"
    assert result.regions[0].name == "East"


def test_dimension_share_is_none_when_total_sales_is_zero() -> None:
    rows = (
        sales_row(2, "2026-01-01", "A", "Office", "North", 0, "10"),
        sales_row(3, "2026-01-02", "B", "Home", "South", 0, "20"),
    )

    assert all(item.sales_share is None for item in analyze_rows(rows).products)


def test_top_and_bottom_rankings_limit_five_with_ties() -> None:
    rows = tuple(
        sales_row(index + 2, "2026-01-01", name, "Office", "North", 1, price)
        for index, (name, price) in enumerate(
            [("F", "1"), ("E", "2"), ("D", "3"), ("C", "4"), ("B", "5"), ("A", "5")]
        )
    )
    result = analyze_rows(rows)

    assert [item.name for item in result.top_products] == ["A", "B", "C", "D", "E"]
    assert [item.name for item in result.bottom_products] == ["F", "E", "D", "C", "A"]
    assert len({item.name for item in result.bottom_products}) == 5


def test_rankings_under_five_return_each_product_once() -> None:
    rows = (
        sales_row(2, "2026-01-01", "B", "Office", "North", 1, "1"),
        sales_row(3, "2026-01-01", "A", "Office", "North", 1, "2"),
    )
    result = analyze_rows(rows)

    assert len(result.top_products) == 2
    assert len(result.bottom_products) == 2
    assert len({item.name for item in result.top_products}) == 2


def test_category_change_uses_amount_and_only_shared_categories() -> None:
    rows = (
        sales_row(2, "2026-01-01", "A", "Growth", "North", 1, "10"),
        sales_row(3, "2026-01-01", "B", "Decline", "North", 1, "30"),
        sales_row(4, "2026-01-01", "C", "OldOnly", "North", 1, "100"),
        sales_row(5, "2026-02-01", "A", "Growth", "North", 1, "25"),
        sales_row(6, "2026-02-01", "B", "Decline", "North", 1, "10"),
        sales_row(7, "2026-02-01", "D", "NewOnly", "North", 1, "100"),
    )
    result = analyze_rows(rows)

    growth = result.largest_category_growth
    decline = result.largest_category_decline
    assert growth is not None and growth.name == "Growth"
    assert growth.change_amount == 15
    assert growth.change_pct == 150
    assert decline is not None and decline.name == "Decline"
    assert decline.change_amount == -20


def test_category_change_previous_zero_has_no_percentage() -> None:
    rows = (
        sales_row(2, "2026-01-01", "A", "Office", "North", 0, "10"),
        sales_row(3, "2026-02-01", "A", "Office", "North", 1, "10"),
    )

    assert analyze_rows(rows).largest_category_growth.change_pct is None


def test_category_change_requires_two_months_and_shared_category() -> None:
    single_month = (
        sales_row(2, "2026-01-01", "A", "Office", "North", 1, "10"),
    )
    separate = (
        sales_row(2, "2026-01-01", "A", "Old", "North", 1, "10"),
        sales_row(3, "2026-02-01", "B", "New", "North", 1, "10"),
    )

    assert analyze_rows(single_month).largest_category_growth is None
    assert analyze_rows(separate).largest_category_decline is None


def test_quality_counts_duplicates_without_removing_them() -> None:
    duplicate = sales_row(2, "2026-01-01", "A", "Office", "North", 1, "10", customer_type=None)
    repeated = duplicate.model_copy(update={"row_number": 3})
    result = analyze_rows((duplicate, repeated), total_rows=3, invalid_rows=1)

    assert result.kpis.transaction_count == 2
    assert result.quality.total_rows == 3
    assert result.quality.valid_rows == 2
    assert result.quality.invalid_rows == 1
    assert result.quality.duplicate_rows == 1
    assert result.quality.missing_optional_values == 2
