from decimal import Decimal
from xml.etree import ElementTree

from app.presentation.html_report_renderer import MAX_HTML_REPORT_BYTES, HtmlReportRenderer
from app.presentation.report_charts import (
    LABEL_LIMIT,
    ReportChart,
    ReportChartAssets,
    build_report_charts,
)
from app.services.report_builder import build_business_report
from tests.test_ai_context import _results


def _report():
    analysis, insights = _results()
    return build_business_report(analysis, insights)


def _assert_accessible_svg(chart: ReportChart) -> None:
    svg = str(chart.svg)
    root = ElementTree.fromstring(svg)
    assert root.tag == "svg"
    assert root.attrib["role"] == "img"
    assert root.attrib["aria-label"] == chart.aria_label
    assert root.find("title") is not None
    assert root.find("desc") is not None


def test_builder_creates_five_accessible_svg_charts() -> None:
    charts = build_report_charts(_report())

    assert isinstance(charts, ReportChartAssets)
    assert charts.monthly_sales.title == "Monthly Sales"
    assert charts.monthly_quantity.title == "Monthly Quantity"
    assert charts.top_products.title == "Top Products by Sales"
    assert charts.categories.title == "Sales by Category"
    assert charts.regions.title == "Sales by Region"
    for chart in (
        charts.monthly_sales,
        charts.monthly_quantity,
        charts.top_products,
        charts.categories,
        charts.regions,
    ):
        _assert_accessible_svg(chart)


def test_monthly_charts_render_lines_bars_and_imputed_status() -> None:
    report = _report()
    source = report.monthly[0]
    imputed = source.model_copy(
        update={
            "year_month": "2026-02",
            "sales": Decimal(0),
            "quantity": 0,
            "is_imputed": True,
        }
    )
    report = report.model_copy(update={"monthly": (source, imputed)})

    charts = build_report_charts(report)

    assert "<polyline" in charts.monthly_sales.svg
    assert "<circle" in charts.monthly_sales.svg
    assert "<rect" in charts.monthly_quantity.svg
    assert 'stroke-dasharray="' in charts.monthly_sales.svg
    assert "No source rows / imputed zero" in charts.monthly_sales.svg


def test_chart_labels_use_existing_decimal_formatter() -> None:
    report = _report()
    precise = report.top_products[0].model_copy(
        update={"sales": Decimal("1234.56789123456789")}
    )
    report = report.model_copy(update={"top_products": (precise,)})

    svg = str(build_report_charts(report).top_products.svg)

    assert "1,234.57" in svg
    assert "1234.56789123456789" not in svg


def test_empty_single_and_zero_datasets_render_safely() -> None:
    report = _report()
    empty = report.model_copy(
        update={
            "monthly": (),
            "top_products": (),
            "top_categories": (),
            "top_regions": (),
        }
    )
    empty_charts = build_report_charts(empty)
    assert "No chart data available" in empty_charts.monthly_sales.svg
    assert "No chart data available" in empty_charts.top_products.svg

    one_zero = report.monthly[0].model_copy(
        update={"sales": Decimal(0), "quantity": 0}
    )
    single = report.model_copy(update={"monthly": (one_zero,)})
    single_charts = build_report_charts(single)
    _assert_accessible_svg(single_charts.monthly_sales)
    _assert_accessible_svg(single_charts.monthly_quantity)
    assert "<circle" in single_charts.monthly_sales.svg
    assert "<rect" in single_charts.monthly_quantity.svg


def test_long_dimension_label_is_truncated_only_for_visible_text() -> None:
    report = _report()
    long_name = "Extremely Long Product Name " * 12
    product = report.top_products[0].model_copy(update={"name": long_name})
    report = report.model_copy(update={"top_products": (product,)})

    chart = build_report_charts(report).top_products

    assert f"{long_name[: LABEL_LIMIT - 1]}..." in chart.svg
    assert long_name in chart.description
    assert 'viewBox="0 0 760' in chart.svg


def test_malicious_dimension_labels_cannot_change_svg_structure() -> None:
    report = _report()
    attacks = (
        "<script>alert(1)</script>",
        "</text><script>alert(1)</script>",
        '\"><image href="https://evil.example/x">',
    )
    product = report.top_products[0].model_copy(update={"name": attacks[0]})
    category = report.top_categories[0].model_copy(update={"name": attacks[1]})
    region = report.top_regions[0].model_copy(update={"name": attacks[2]})
    report = report.model_copy(
        update={
            "top_products": (product,),
            "top_categories": (category,),
            "top_regions": (region,),
        }
    )

    charts = build_report_charts(report)
    svg = "".join(
        str(chart.svg)
        for chart in (charts.top_products, charts.categories, charts.regions)
    ).lower()

    assert "<script" not in svg
    assert "<foreignobject" not in svg
    assert "<image" not in svg
    assert "href=" not in svg
    assert "javascript:" not in svg
    assert "onload=" not in svg
    assert "onerror=" not in svg
    for chart in (charts.top_products, charts.categories, charts.regions):
        _assert_accessible_svg(chart)


def test_chart_output_is_deterministic() -> None:
    report = _report()

    assert build_report_charts(report) == build_report_charts(report)


def test_html_report_contains_five_charts_and_existing_tables() -> None:
    html = HtmlReportRenderer().render(_report())
    encoded = html.encode("utf-8")

    assert html.count("<svg ") == 5
    for chart_id in (
        "report-monthly-sales",
        "report-monthly-quantity",
        "report-top-products",
        "report-categories",
        "report-regions",
    ):
        assert f'id="{chart_id}"' in html
    assert html.count("<table>") >= 5
    assert "Monthly Performance" in html
    assert "Product Performance" in html
    assert len(encoded) < MAX_HTML_REPORT_BYTES
    assert "<script" not in html.lower()
    assert "<foreignobject" not in html.lower()
    assert "javascript:" not in html.lower()
