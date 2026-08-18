from enum import StrEnum
from typing import NoReturn

from app.domain.report_models import BusinessReport
from app.presentation.html_report_renderer import HtmlReportRenderer
from app.presentation.report_charts import ReportChartAssets

MAX_PDF_REPORT_BYTES = 5_000_000


class PdfErrorCode(StrEnum):
    RENDER_FAILED = "PDF_RENDER_FAILED"
    TOO_LARGE = "PDF_TOO_LARGE"
    BUSY = "PDF_BUSY"
    RATE_LIMITED = "PDF_RATE_LIMITED"


class PdfReportError(Exception):
    def __init__(self, code: PdfErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


def reject_external_url(url: str, *args: object, **kwargs: object) -> NoReturn:
    """Reject every fetch because report HTML has no external resources."""
    raise PdfReportError(PdfErrorCode.RENDER_FAILED)


def _create_pdf_document(html: str):
    try:
        from weasyprint import HTML
    except Exception as exc:
        raise PdfReportError(PdfErrorCode.RENDER_FAILED) from exc
    return HTML(string=html, url_fetcher=reject_external_url)


class PdfReportRenderer:
    def __init__(self, html_renderer: HtmlReportRenderer | None = None) -> None:
        self._html_renderer = html_renderer or HtmlReportRenderer()

    def render_pdf(
        self,
        report: BusinessReport,
        charts: ReportChartAssets | None = None,
    ) -> bytes:
        try:
            html = self._html_renderer.render(report, charts)
            output = _create_pdf_document(html).write_pdf()
        except PdfReportError:
            raise
        except Exception as exc:
            raise PdfReportError(PdfErrorCode.RENDER_FAILED) from exc

        if not isinstance(output, bytes) or not output.startswith(b"%PDF-"):
            raise PdfReportError(PdfErrorCode.RENDER_FAILED)
        if len(output) > MAX_PDF_REPORT_BYTES:
            raise PdfReportError(PdfErrorCode.TOO_LARGE)
        return output
