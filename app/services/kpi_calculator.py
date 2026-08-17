from decimal import Decimal, localcontext

import pandas as pd

from app.domain.models import KpiSummary

DECIMAL_PRECISION = 256
HUNDRED = Decimal("100")


def decimal_ratio(numerator: Decimal | int, denominator: Decimal | int) -> Decimal | None:
    if denominator == 0:
        return None
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        return Decimal(numerator) / Decimal(denominator)


def decimal_percentage(
    numerator: Decimal | int, denominator: Decimal | int
) -> Decimal | None:
    ratio = decimal_ratio(numerator, denominator)
    return None if ratio is None else ratio * HUNDRED


def calculate_kpis(frame: pd.DataFrame) -> KpiSummary:
    transaction_count = len(frame)
    total_sales = sum(frame["sales"], start=Decimal("0"))
    total_quantity = int(frame["quantity"].sum()) if transaction_count else 0

    return KpiSummary(
        total_sales=total_sales,
        total_quantity=total_quantity,
        transaction_count=transaction_count,
        average_order_value=decimal_ratio(total_sales, transaction_count),
        average_unit_price=decimal_ratio(total_sales, total_quantity),
        unique_products=int(frame["product"].nunique()),
        unique_categories=int(frame["category"].nunique()),
        unique_regions=int(frame["region"].nunique()),
    )
