from dataclasses import dataclass
from decimal import Decimal
from html import escape
import re

from markupsafe import Markup

from app.domain.models import DimensionMetric, MonthlyMetric
from app.domain.report_models import BusinessReport
from app.presentation.formatters import format_decimal, format_integer

SVG_WIDTH = 760
MONTHLY_HEIGHT = 300
DIMENSION_LIMIT = 10
LABEL_LIMIT = 24
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class ReportChart:
    id: str
    title: str
    svg: Markup
    aria_label: str
    description: str


@dataclass(frozen=True, slots=True)
class ReportChartAssets:
    monthly_sales: ReportChart
    monthly_quantity: ReportChart
    top_products: ReportChart
    categories: ReportChart
    regions: ReportChart


def _xml_text(value: str) -> str:
    cleaned = _CONTROL_CHARACTERS.sub("", value)
    escaped = escape(cleaned, quote=True).replace("=", "&#61;")
    return re.sub(r"(?i)javascript:", "javascript&#58;", escaped)


def _truncate(value: str) -> str:
    return value if len(value) <= LABEL_LIMIT else f"{value[: LABEL_LIMIT - 1]}..."


def _coordinate(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.1')):f}"


def _svg_document(
    *, chart_id: str, title: str, aria_label: str, description: str, body: str, height: int
) -> Markup:
    return Markup(
        f'<svg id="{chart_id}" '
        f'viewBox="0 0 {SVG_WIDTH} {height}" role="img" '
        f'aria-label="{_xml_text(aria_label)}">'
        f"<title>{_xml_text(title)}</title><desc>{_xml_text(description)}</desc>"
        f'<rect width="{SVG_WIDTH}" height="{height}" fill="#ffffff"/>{body}</svg>'
    )


def _empty_chart(chart_id: str, title: str, aria_label: str) -> ReportChart:
    description = "No chart data available."
    body = (
        '<rect x="24" y="24" width="712" height="172" fill="#f8fafb" '
        'stroke="#dce2e6"/><text x="380" y="112" text-anchor="middle" '
        'font-family="Arial, sans-serif" font-size="14" fill="#65717c">'
        "No chart data available</text>"
    )
    return ReportChart(
        id=chart_id,
        title=title,
        svg=_svg_document(
            chart_id=chart_id,
            title=title,
            aria_label=aria_label,
            description=description,
            body=body,
            height=220,
        ),
        aria_label=aria_label,
        description=description,
    )


def _monthly_chart(
    metrics: tuple[MonthlyMetric, ...], *, value_name: str, chart_id: str, title: str
) -> ReportChart:
    aria_label = f"{title} chart"
    if not metrics:
        return _empty_chart(chart_id, title, aria_label)

    values = tuple(
        metric.sales if value_name == "sales" else Decimal(metric.quantity)
        for metric in metrics
    )
    maximum = max(values)
    scale_max = maximum if maximum > 0 else Decimal(1)
    left, top, plot_width, plot_height = 62, 28, 670, 205
    denominator = max(len(metrics) - 1, 1)
    x_positions = tuple(
        Decimal(left) + Decimal(index) * Decimal(plot_width) / Decimal(denominator)
        for index in range(len(metrics))
    )
    y_positions = tuple(
        Decimal(top + plot_height) - value * Decimal(plot_height) / scale_max
        for value in values
    )
    parts = [
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#52606b"/>',
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}" stroke="#52606b"/>',
    ]
    for index in range(5):
        y = Decimal(top) + Decimal(index) * Decimal(plot_height) / Decimal(4)
        grid_value = scale_max * Decimal(4 - index) / Decimal(4)
        parts.append(
            f'<line x1="{left}" y1="{_coordinate(y)}" x2="{left + plot_width}" '
            f'y2="{_coordinate(y)}" stroke="#dce2e6"/>'
            f'<text x="{left - 8}" y="{_coordinate(y + Decimal(4))}" text-anchor="end" '
            f'font-family="Arial, sans-serif" font-size="10" fill="#65717c">'
            f'{_xml_text(format_decimal(grid_value) if value_name == "sales" else format_integer(int(grid_value)))}</text>'
        )

    if value_name == "sales":
        points = " ".join(
            f"{_coordinate(x)},{_coordinate(y)}"
            for x, y in zip(x_positions, y_positions, strict=True)
        )
        if len(metrics) > 1:
            parts.append(
                f'<polyline points="{points}" fill="none" stroke="#238570" '
                'stroke-width="2.5"/>'
            )
        for metric, x, y in zip(metrics, x_positions, y_positions, strict=True):
            fill = "#ffffff" if metric.is_imputed else "#238570"
            dash = ' stroke-dasharray="2 2"' if metric.is_imputed else ""
            parts.append(
                f'<circle cx="{_coordinate(x)}" cy="{_coordinate(y)}" r="4" '
                f'fill="{fill}" stroke="#238570" stroke-width="2"{dash}/>'
            )
    else:
        slot_width = Decimal(plot_width) / Decimal(len(metrics))
        bar_width = max(Decimal(4), min(Decimal(34), slot_width * Decimal("0.62")))
        for metric, value, x, y in zip(
            metrics, values, x_positions, y_positions, strict=True
        ):
            height = Decimal(top + plot_height) - y
            fill = "#ffffff" if metric.is_imputed else "#4f7894"
            dash = ' stroke-dasharray="3 2"' if metric.is_imputed else ""
            parts.append(
                f'<rect x="{_coordinate(x - bar_width / 2)}" y="{_coordinate(y)}" '
                f'width="{_coordinate(bar_width)}" height="{_coordinate(height)}" '
                f'fill="{fill}" stroke="#4f7894"{dash}/>'
            )

    label_step = max(1, (len(metrics) + 11) // 12)
    for index, (metric, x) in enumerate(zip(metrics, x_positions, strict=True)):
        if index % label_step == 0 or index == len(metrics) - 1:
            parts.append(
                f'<text x="{_coordinate(x)}" y="252" text-anchor="end" '
                f'transform="rotate(-35 {_coordinate(x)} 252)" '
                f'font-family="Arial, sans-serif" font-size="9" fill="#52606b">'
                f"{_xml_text(metric.year_month)}</text>"
            )

    imputed = sum(metric.is_imputed for metric in metrics)
    value_label = "sales" if value_name == "sales" else "quantity"
    description = (
        f"{title} for {len(metrics)} months. {imputed} month(s) have "
        "No source rows / imputed zero. "
        + "; ".join(
            f"{metric.year_month}: "
            f"{format_decimal(value) if value_name == 'sales' else format_integer(int(value))}"
            for metric, value in zip(metrics, values, strict=True)
        )
        + f" {value_label}."
    )
    return ReportChart(
        id=chart_id,
        title=title,
        svg=_svg_document(
            chart_id=chart_id,
            title=title,
            aria_label=aria_label,
            description=description,
            body="".join(parts),
            height=MONTHLY_HEIGHT,
        ),
        aria_label=aria_label,
        description=description,
    )


def _dimension_chart(
    metrics: tuple[DimensionMetric, ...], *, chart_id: str, title: str
) -> ReportChart:
    aria_label = f"{title} chart"
    items = metrics[:DIMENSION_LIMIT]
    if not items:
        return _empty_chart(chart_id, title, aria_label)

    maximum = max(item.sales for item in items)
    scale_max = maximum if maximum > 0 else Decimal(1)
    row_height, top, label_x, bar_x, bar_width = 34, 28, 188, 205, 500
    height = top * 2 + row_height * len(items)
    parts: list[str] = []
    for index, item in enumerate(items):
        y = top + index * row_height
        width = item.sales * Decimal(bar_width) / scale_max
        parts.extend(
            (
                f'<text x="{label_x}" y="{y + 15}" text-anchor="end" '
                f'font-family="Arial, sans-serif" font-size="11" fill="#26343e">'
                f"{_xml_text(_truncate(item.name))}</text>",
                f'<rect x="{bar_x}" y="{y}" width="{bar_width}" height="20" '
                'fill="#f0f4f5"/>',
                f'<rect x="{bar_x}" y="{y}" width="{_coordinate(width)}" height="20" '
                'fill="#238570"/>',
                f'<text x="{bar_x + 7}" y="{y + 14}" font-family="Arial, sans-serif" '
                f'font-size="10" fill="#17202a">{_xml_text(format_decimal(item.sales))}</text>',
            )
        )
    description = f"{title}. " + "; ".join(
        f"{item.name}: {format_decimal(item.sales)}" for item in items
    )
    return ReportChart(
        id=chart_id,
        title=title,
        svg=_svg_document(
            chart_id=chart_id,
            title=title,
            aria_label=aria_label,
            description=description,
            body="".join(parts),
            height=height,
        ),
        aria_label=aria_label,
        description=description,
    )


def build_report_charts(report: BusinessReport) -> ReportChartAssets:
    return ReportChartAssets(
        monthly_sales=_monthly_chart(
            report.monthly,
            value_name="sales",
            chart_id="report-monthly-sales",
            title="Monthly Sales",
        ),
        monthly_quantity=_monthly_chart(
            report.monthly,
            value_name="quantity",
            chart_id="report-monthly-quantity",
            title="Monthly Quantity",
        ),
        top_products=_dimension_chart(
            report.top_products,
            chart_id="report-top-products",
            title="Top Products by Sales",
        ),
        categories=_dimension_chart(
            report.top_categories,
            chart_id="report-categories",
            title="Sales by Category",
        ),
        regions=_dimension_chart(
            report.top_regions,
            chart_id="report-regions",
            title="Sales by Region",
        ),
    )
