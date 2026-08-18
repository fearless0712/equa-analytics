import asyncio
import csv
from io import StringIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.presentation.html_report_renderer import HtmlReportRenderer
from app.presentation.pdf_report_renderer import (
    MAX_PDF_REPORT_BYTES,
    PdfErrorCode,
    PdfReportError,
    PdfReportRenderer,
    reject_external_url,
)
from app.presentation.report_charts import build_report_charts
from app.services.report_builder import build_business_report
from tests.test_ai_context import _results

SAMPLE = Path("sample_data/valid_sales.csv").read_bytes()


def _report():
    analysis, insights = _results()
    return build_business_report(analysis, insights)


def test_pdf_renderer_generates_nonempty_pdf_from_five_svg_report() -> None:
    report = _report()
    charts = build_report_charts(report)
    html = HtmlReportRenderer().render(report, charts)

    output = PdfReportRenderer().render_pdf(report, charts)

    assert html.count("<svg ") == 5
    assert output.startswith(b"%PDF-")
    assert len(output) > 1_000
    assert len(output) < MAX_PDF_REPORT_BYTES
    assert report.ai is None


def test_external_url_fetcher_rejects_every_scheme_without_disclosure() -> None:
    for url in (
        "https://example.invalid/resource",
        "http://example.invalid/resource",
        "file:///private/value",
        "ftp://example.invalid/resource",
        "data:text/plain,private",
    ):
        with pytest.raises(PdfReportError) as exc_info:
            reject_external_url(url)
        assert exc_info.value.code is PdfErrorCode.RENDER_FAILED
        assert url not in str(exc_info.value)


def test_pdf_renderer_maps_internal_exception_to_safe_code(monkeypatch) -> None:
    def broken_document(html):
        raise RuntimeError("PRIVATE_INTERNAL_HTML")

    monkeypatch.setattr(
        "app.presentation.pdf_report_renderer._create_pdf_document",
        broken_document,
    )

    with pytest.raises(PdfReportError) as exc_info:
        PdfReportRenderer().render_pdf(_report())

    assert exc_info.value.code is PdfErrorCode.RENDER_FAILED
    assert "PRIVATE_INTERNAL_HTML" not in str(exc_info.value)


def test_pdf_renderer_enforces_generated_byte_limit(monkeypatch) -> None:
    monkeypatch.setattr("app.presentation.pdf_report_renderer.MAX_PDF_REPORT_BYTES", 1)

    with pytest.raises(PdfReportError) as exc_info:
        PdfReportRenderer().render_pdf(_report())

    assert exc_info.value.code is PdfErrorCode.TOO_LARGE


def test_pdf_download_returns_safe_attachment(client: TestClient) -> None:
    response = client.post(
        "/reports/pdf",
        files={"file": ("private-company-name.csv", SAMPLE, "text/csv")},
    )

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-")
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="equa-analytics-report-'
    )
    assert response.headers["content-disposition"].endswith('.pdf"')
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert b"private-company-name" not in response.content
    assert b"OPENAI_API_KEY" not in response.content


def test_pdf_route_rejects_invalid_csv_safely(client: TestClient) -> None:
    private = "PRIVATE_RAW_ROW"
    response = client.post(
        "/reports/pdf",
        files={
            "file": (
                "sales.csv",
                f"date,product\n2026-01-01,{private}\n".encode(),
                "text/csv",
            )
        },
    )

    assert response.status_code == 422
    assert "CSV_MISSING_REQUIRED_COLUMN" in response.text
    assert private not in response.text
    assert "Traceback" not in response.text


def test_pdf_route_rejects_oversized_csv_with_413(client: TestClient) -> None:
    response = client.post(
        "/reports/pdf",
        files={
            "file": (
                "sales.csv",
                b"x" * (5 * 1024 * 1024 + 1),
                "text/csv",
            )
        },
    )

    assert response.status_code == 413
    assert "CSV_FILE_TOO_LARGE" in response.text


def test_pdf_route_maps_size_failure_to_fixed_413(client: TestClient, monkeypatch) -> None:
    def too_large(report):
        raise PdfReportError(PdfErrorCode.TOO_LARGE)

    monkeypatch.setattr(
        "app.web.routes.pdf_report_renderer.render_pdf", too_large
    )
    response = client.post(
        "/reports/pdf", files={"file": ("sales.csv", SAMPLE, "text/csv")}
    )

    assert response.status_code == 413
    assert response.json() == {
        "code": "PDF_TOO_LARGE",
        "message": "PDF report exceeds the safe size limit.",
    }
    assert "Traceback" not in response.text


def test_pdf_route_hides_renderer_exception(client: TestClient, monkeypatch) -> None:
    def failed(report):
        raise PdfReportError(PdfErrorCode.RENDER_FAILED)

    monkeypatch.setattr("app.web.routes.pdf_report_renderer.render_pdf", failed)
    response = client.post(
        "/reports/pdf", files={"file": ("sales.csv", SAMPLE, "text/csv")}
    )

    assert response.status_code == 500
    assert response.json() == {
        "code": "PDF_RENDER_FAILED",
        "message": "PDF report generation failed.",
    }
    assert "Traceback" not in response.text


def test_pdf_route_has_dedicated_two_request_rate_limit(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.web.routes.pdf_report_renderer.render_pdf", lambda report: b"%PDF-test"
    )
    statuses = [
        client.post(
            "/reports/pdf", files={"file": ("sales.csv", SAMPLE, "text/csv")}
        ).status_code
        for _ in range(3)
    ]

    assert statuses == [200, 200, 429]


def test_pdf_route_rejects_concurrent_generation_as_busy(
    client: TestClient,
) -> None:
    semaphore = client.app.state.pdf_semaphore
    asyncio.run(semaphore.acquire())
    try:
        response = client.post(
            "/reports/pdf", files={"file": ("sales.csv", SAMPLE, "text/csv")}
        )
    finally:
        semaphore.release()

    assert response.status_code == 503
    assert response.json()["code"] == "PDF_BUSY"


def test_pdf_pipeline_escapes_xss_and_excludes_customer_detail(
    client: TestClient, monkeypatch
) -> None:
    captured: dict[str, str] = {}

    def capture_html(report):
        captured["html"] = HtmlReportRenderer().render(report)
        return b"%PDF-test"

    monkeypatch.setattr(
        "app.web.routes.pdf_report_renderer.render_pdf", capture_html
    )
    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(
        ["date", "product", "category", "region", "quantity", "unit_price", "customer_type"]
    )
    writer.writerow(
        [
            "2026-01-01",
            "<script>alert(1)</script>",
            "</text><script>alert(2)</script>",
            '\"><image href="https://evil.example/x">',
            "1",
            "10",
            "CONFIDENTIAL_CUSTOMER_DETAIL",
        ]
    )

    response = client.post(
        "/reports/pdf",
        files={"file": ("private.csv", stream.getvalue().encode(), "text/csv")},
    )

    assert response.status_code == 200
    html = captured["html"]
    assert html.lower().count("<script") == 0
    assert "CONFIDENTIAL_CUSTOMER_DETAIL" not in html
    assert "private.csv" not in html
    assert "raw_rows" not in html
    assert "AI context" not in html


def test_dashboard_keeps_html_and_adds_pdf_download(client: TestClient) -> None:
    response = client.post(
        "/dashboard", files={"file": ("sales.csv", SAMPLE, "text/csv")}
    )

    assert response.status_code == 200
    assert 'action="/reports/html"' in response.text
    assert 'action="/reports/pdf"' in response.text
    assert "Download HTML Report" in response.text
    assert "Download PDF Report" in response.text
