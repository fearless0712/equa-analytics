from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.domain.report_models import BusinessReport
from app.presentation.formatters import (
    format_ai_evidence,
    format_decimal,
    format_insight_evidence,
    format_insight_summary,
    format_integer,
    format_percentage,
    format_signed_number,
    format_signed_percentage,
)
from app.presentation.report_charts import ReportChartAssets, build_report_charts

APP_DIR = Path(__file__).resolve().parents[1]
REPORT_CSS_MARKER = "/*__EQUA_REPORT_CSS__*/"
MAX_HTML_REPORT_BYTES = 2_000_000


class HtmlReportTooLargeError(Exception):
    """Raised when the final encoded report exceeds the delivery limit."""


class HtmlReportRenderer:
    def __init__(self) -> None:
        self._environment = Environment(
            loader=FileSystemLoader(APP_DIR / "templates"),
            autoescape=select_autoescape(("html", "xml")),
        )
        self._environment.filters.update(
            ai_evidence=format_ai_evidence,
            decimal=format_decimal,
            insight_evidence=format_insight_evidence,
            insight_summary=format_insight_summary,
            integer=format_integer,
            percentage=format_percentage,
            signed_number=format_signed_number,
            signed_percentage=format_signed_percentage,
        )
        self._template = self._environment.get_template(
            "reports/business_report.html"
        )
        self._css = (APP_DIR / "static" / "css" / "report.css").read_text(
            encoding="utf-8"
        )

    def render(
        self, report: BusinessReport, charts: ReportChartAssets | None = None
    ) -> str:
        chart_assets = charts or build_report_charts(report)
        rendered = self._template.render(report=report, charts=chart_assets)
        return rendered.replace(REPORT_CSS_MARKER, self._css, 1)

    def render_bytes(
        self, report: BusinessReport, charts: ReportChartAssets | None = None
    ) -> bytes:
        content = self.render(report, charts).encode("utf-8")
        if len(content) > MAX_HTML_REPORT_BYTES:
            raise HtmlReportTooLargeError
        return content
