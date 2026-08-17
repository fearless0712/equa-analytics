from decimal import Decimal, localcontext

import pandas as pd

from app.domain.models import (
    AnalysisResult,
    CategoryChange,
    DataQualityReport,
    DimensionMetric,
    MonthlyMetric,
    NormalizedSalesRow,
)
from app.services.kpi_calculator import (
    DECIMAL_PRECISION,
    calculate_kpis,
    decimal_percentage,
)

ANALYSIS_COLUMNS = (
    "date",
    "product",
    "category",
    "region",
    "quantity",
    "unit_price",
    "discount",
    "customer_type",
    "sales",
)
RANKING_LIMIT = 5


def rows_to_dataframe(rows: tuple[NormalizedSalesRow, ...]) -> pd.DataFrame:
    records = [
        {column: getattr(row, column) for column in ANALYSIS_COLUMNS} for row in rows
    ]
    return pd.DataFrame.from_records(records, columns=ANALYSIS_COLUMNS)


def _monthly_metrics(frame: pd.DataFrame) -> tuple[MonthlyMetric, ...]:
    if frame.empty:
        return ()

    periods = pd.PeriodIndex(pd.to_datetime(frame["date"]), freq="M")
    working = frame.assign(year_month=periods)
    grouped = working.groupby("year_month", sort=True).agg(
        sales=("sales", "sum"),
        quantity=("quantity", "sum"),
        transaction_count=("sales", "size"),
    )
    calendar = pd.period_range(grouped.index.min(), grouped.index.max(), freq="M")
    observed = set(grouped.index)
    metrics: list[MonthlyMetric] = []
    previous_sales: Decimal | None = None
    previous_quantity: int | None = None

    for period in calendar:
        if period in observed:
            sales = grouped.at[period, "sales"]
            quantity = int(grouped.at[period, "quantity"])
            transaction_count = int(grouped.at[period, "transaction_count"])
            is_imputed = False
        else:
            sales = Decimal("0")
            quantity = 0
            transaction_count = 0
            is_imputed = True

        sales_change = None if previous_sales is None else sales - previous_sales
        quantity_change = (
            None if previous_quantity is None else quantity - previous_quantity
        )
        metrics.append(
            MonthlyMetric(
                year_month=str(period),
                sales=sales,
                quantity=quantity,
                transaction_count=transaction_count,
                sales_change=sales_change,
                sales_change_pct=(
                    None
                    if sales_change is None
                    else decimal_percentage(sales_change, previous_sales)
                ),
                quantity_change=quantity_change,
                quantity_change_pct=(
                    None
                    if quantity_change is None
                    else decimal_percentage(quantity_change, previous_quantity)
                ),
                is_imputed=is_imputed,
            )
        )
        previous_sales = sales
        previous_quantity = quantity

    return tuple(metrics)


def _dimension_metrics(
    frame: pd.DataFrame, dimension: str, total_sales: Decimal
) -> tuple[DimensionMetric, ...]:
    if frame.empty:
        return ()
    grouped = frame.groupby(dimension, sort=False).agg(
        sales=("sales", "sum"),
        quantity=("quantity", "sum"),
        transaction_count=("sales", "size"),
    )
    records = [
        (str(name), row["sales"], int(row["quantity"]), int(row["transaction_count"]))
        for name, row in grouped.iterrows()
    ]
    records.sort(key=lambda item: (-item[1], item[0]))
    return tuple(
        DimensionMetric(
            name=name,
            sales=sales,
            quantity=quantity,
            transaction_count=count,
            sales_share=decimal_percentage(sales, total_sales),
            rank=rank,
        )
        for rank, (name, sales, quantity, count) in enumerate(records, start=1)
    )


def _product_rankings(
    products: tuple[DimensionMetric, ...],
) -> tuple[tuple[DimensionMetric, ...], tuple[DimensionMetric, ...]]:
    top = products[:RANKING_LIMIT]
    bottom = tuple(
        sorted(products, key=lambda metric: (metric.sales, metric.name))[:RANKING_LIMIT]
    )
    return top, bottom


def _category_changes(
    frame: pd.DataFrame,
) -> tuple[CategoryChange | None, CategoryChange | None]:
    if frame.empty:
        return None, None
    periods = pd.PeriodIndex(pd.to_datetime(frame["date"]), freq="M")
    working = frame.assign(year_month=periods)
    available_months = sorted(working["year_month"].unique())
    if len(available_months) < 2:
        return None, None

    previous_month, current_month = available_months[-2:]
    grouped = working.groupby(["year_month", "category"], sort=False)["sales"].sum()
    previous_categories = set(grouped.loc[previous_month].index)
    current_categories = set(grouped.loc[current_month].index)
    comparable = sorted(previous_categories & current_categories)
    if not comparable:
        return None, None

    changes: list[CategoryChange] = []
    for name in comparable:
        previous_sales = grouped.loc[(previous_month, name)]
        current_sales = grouped.loc[(current_month, name)]
        change = current_sales - previous_sales
        changes.append(
            CategoryChange(
                name=str(name),
                current_month=str(current_month),
                previous_month=str(previous_month),
                current_sales=current_sales,
                previous_sales=previous_sales,
                change_amount=change,
                change_pct=decimal_percentage(change, previous_sales),
            )
        )

    growth = sorted(changes, key=lambda item: (-item.change_amount, item.name))[0]
    decline = sorted(changes, key=lambda item: (item.change_amount, item.name))[0]
    return growth, decline


def _quality_report(
    frame: pd.DataFrame, total_rows: int, invalid_rows: int
) -> DataQualityReport:
    duplicate_subset = list(ANALYSIS_COLUMNS[:-1])
    duplicate_rows = int(frame.duplicated(subset=duplicate_subset, keep="first").sum())
    missing_optional = int(frame["customer_type"].isna().sum())
    return DataQualityReport(
        total_rows=total_rows,
        valid_rows=len(frame),
        invalid_rows=invalid_rows,
        duplicate_rows=duplicate_rows,
        missing_optional_values=missing_optional,
    )


def analyze_rows(
    rows: tuple[NormalizedSalesRow, ...],
    *,
    total_rows: int | None = None,
    invalid_rows: int = 0,
) -> AnalysisResult:
    frame = rows_to_dataframe(rows)
    source_total = len(rows) + invalid_rows if total_rows is None else total_rows
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        kpis = calculate_kpis(frame)
        products = _dimension_metrics(frame, "product", kpis.total_sales)
        categories = _dimension_metrics(frame, "category", kpis.total_sales)
        regions = _dimension_metrics(frame, "region", kpis.total_sales)
        top_products, bottom_products = _product_rankings(products)
        growth, decline = _category_changes(frame)
        return AnalysisResult(
            kpis=kpis,
            monthly=_monthly_metrics(frame),
            products=products,
            categories=categories,
            regions=regions,
            top_products=top_products,
            bottom_products=bottom_products,
            largest_category_growth=growth,
            largest_category_decline=decline,
            quality=_quality_report(frame, source_total, invalid_rows),
        )
