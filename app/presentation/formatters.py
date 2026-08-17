from decimal import Decimal


def format_decimal(value: Decimal | None) -> str:
    if value is None:
        return "N/A"
    rendered = format(value, "f")
    integer, separator, fraction = rendered.partition(".")
    fraction = fraction.rstrip("0")
    integer_with_separators = f"{int(integer):,}"
    return (
        f"{integer_with_separators}.{fraction}"
        if separator and fraction
        else integer_with_separators
    )


def format_integer(value: int) -> str:
    return f"{value:,}"


def format_percentage(value: Decimal | None) -> str:
    return "N/A" if value is None else f"{format_decimal(value)}%"
