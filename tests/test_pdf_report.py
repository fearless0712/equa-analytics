import asyncio
import csv
import json
import logging
from io import StringIO
from pathlib import Path
from threading import Event, Lock
from concurrent.futures import ThreadPoolExecutor
import time

import pytest
from fastapi.testclient import TestClient

from app.presentation.html_report_renderer import HtmlReportRenderer
from app.ai.context_builder import build_ai_context
from app.ai.fake_ai import FakeAiProvider
from app.presentation.pdf_report_renderer import (
    MAX_PDF_REPORT_BYTES,
    PdfErrorCode,
    PdfReportError,
    PdfReportRenderer,
    reject_external_url,
)
from app.presentation.report_charts import build_report_charts
from app.config import Environment, Settings
from app.main import create_app
from app.services.report_builder import build_business_report
from tests.test_ai_context import _results

SAMPLE = Path("sample_data/valid_sales.csv").read_bytes()


def _report():
    analysis, insights = _results()
    return build_business_report(analysis, insights)


def test_pdf_semaphore_is_initialized_unlocked_during_lifespan() -> None:
    application = create_app(Settings(environment=Environment.TEST))

    assert not hasattr(application.state, "pdf_semaphore")
    with TestClient(application):
        assert application.state.pdf_semaphore.locked() is False


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


def test_pdf_renderer_uses_the_same_formatted_evidence_html(
    monkeypatch,
) -> None:
    report = _report()
    raw_value = "30.436348667284141195842338170"
    insight = report.insights.business[0].model_copy(
        update={"evidence": (f"top_one_share={raw_value}",)}
    )
    report = report.model_copy(
        update={
            "insights": report.insights.model_copy(update={"business": (insight,)})
        }
    )
    html_renderer = HtmlReportRenderer()
    expected_html = html_renderer.render(report)
    captured: dict[str, str] = {}

    class PdfDocument:
        def write_pdf(self) -> bytes:
            return b"%PDF-test"

    def capture_document(html: str) -> PdfDocument:
        captured["html"] = html
        return PdfDocument()

    monkeypatch.setattr(
        "app.presentation.pdf_report_renderer._create_pdf_document",
        capture_document,
    )

    output = PdfReportRenderer(html_renderer).render_pdf(report)

    assert output == b"%PDF-test"
    assert captured["html"] == expected_html
    assert "Leading share: 30.44%" in captured["html"]
    assert raw_value not in captured["html"]


def test_pdf_source_html_formats_ai_finding_and_recommendation_evidence(
    monkeypatch,
) -> None:
    analysis, insights = _results()
    ai = FakeAiProvider().generate(build_ai_context(analysis, insights))
    finding = ai.key_findings[0].model_copy(
        update={
            "evidence": (
                "monthly[2026-04].sales_change_pct = "
                "-12.514370175726720315322713089; "
                "regions[North].sales_share = "
                "30.436348667284141195842338170217"
            )
        }
    )
    recommendation = ai.recommendations[0].model_copy(
        update={
            "evidence": (
                "Desk Chair sales_share is reported as 27.606257075228980",
                "Office sales 32750 versus 35150.00 previously",
            )
        }
    )
    report = build_business_report(
        analysis,
        insights,
        ai=ai.model_copy(
            update={
                "key_findings": (finding,),
                "recommendations": (recommendation,),
            }
        ),
    )
    actual_output = PdfReportRenderer().render_pdf(report)
    captured: dict[str, str] = {}

    class PdfDocument:
        def write_pdf(self) -> bytes:
            return b"%PDF-ai-evidence"

    def capture_document(html: str) -> PdfDocument:
        captured["html"] = html
        return PdfDocument()

    monkeypatch.setattr(
        "app.presentation.pdf_report_renderer._create_pdf_document",
        capture_document,
    )

    output = PdfReportRenderer().render_pdf(report)

    assert actual_output.startswith(b"%PDF-")
    assert len(actual_output) < MAX_PDF_REPORT_BYTES
    assert output.startswith(b"%PDF-")
    assert "Sales change: -12.51%" in captured["html"]
    assert "North sales share: 30.44%" in captured["html"]
    assert "Desk Chair sales share: 27.61%" in captured["html"]
    assert "Office sales 32,750 versus 35,150 previously" in captured["html"]
    assert "30.436348667284141195842338170217" not in captured["html"]
    assert "-12.514370175726720315322713089" not in captured["html"]
    assert "27.606257075228980" not in captured["html"]


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
    assert client.app.state.pdf_semaphore.locked() is False
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
    assert client.app.state.pdf_semaphore.locked() is False


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
    assert client.app.state.pdf_semaphore.locked() is False


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
    assert client.app.state.pdf_semaphore.locked() is False


def test_pdf_route_releases_slot_after_analysis_exception(
    client: TestClient, monkeypatch
) -> None:
    def failed_analysis(*args, **kwargs):
        raise RuntimeError("PRIVATE_ANALYSIS_EXCEPTION")

    monkeypatch.setattr("app.web.routes.analyze_rows", failed_analysis)
    response = client.post(
        "/reports/pdf", files={"file": ("sales.csv", SAMPLE, "text/csv")}
    )

    assert response.status_code == 500
    assert response.json()["code"] == "PDF_RENDER_FAILED"
    assert "PRIVATE_ANALYSIS_EXCEPTION" not in response.text
    assert client.app.state.pdf_semaphore.locked() is False


def test_pdf_route_has_dedicated_five_request_rate_limit(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.web.routes.pdf_report_renderer.render_pdf", lambda report: b"%PDF-test"
    )
    statuses = [
        client.post(
            "/reports/pdf", files={"file": ("sales.csv", SAMPLE, "text/csv")}
        ).status_code
        for _ in range(6)
    ]

    assert statuses == [200, 200, 200, 200, 200, 429]
    response = client.post(
        "/reports/pdf", files={"file": ("sales.csv", SAMPLE, "text/csv")}
    )
    assert response.status_code == 429
    assert response.json()["code"] == "PDF_RATE_LIMITED"


def test_concurrent_pdf_requests_timeout_then_recover(
    client: TestClient, monkeypatch
) -> None:
    entered = Event()
    allow_completion = Event()
    active_lock = Lock()
    active = 0
    maximum_active = 0

    def blocking_render(report):
        nonlocal active, maximum_active
        with active_lock:
            active += 1
            maximum_active = max(maximum_active, active)
        entered.set()
        assert allow_completion.wait(timeout=5)
        with active_lock:
            active -= 1
        return b"%PDF-test"

    monkeypatch.setattr(
        "app.web.routes.pdf_report_renderer.render_pdf", blocking_render
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            client.post,
            "/reports/pdf",
            files={"file": ("sales.csv", SAMPLE, "text/csv")},
        )
        assert entered.wait(timeout=3)
        started = time.monotonic()
        second = client.post(
            "/reports/pdf", files={"file": ("sales.csv", SAMPLE, "text/csv")}
        )
        waited = time.monotonic() - started
        allow_completion.set()
        first_response = first.result(timeout=5)

    assert first_response.status_code == 200
    assert second.status_code == 503
    assert second.json()["code"] == "PDF_BUSY"
    assert waited >= 1.8
    assert maximum_active == 1
    third = client.post(
        "/reports/pdf", files={"file": ("sales.csv", SAMPLE, "text/csv")}
    )
    assert third.status_code == 200
    assert client.app.state.pdf_semaphore.locked() is False


def test_busy_requests_continue_to_consume_pdf_rate_limit(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr("app.web.routes.PDF_SLOT_TIMEOUT_SECONDS", 0.01)
    semaphore = client.app.state.pdf_semaphore
    asyncio.run(semaphore.acquire())
    try:
        statuses = [
            client.post(
                "/reports/pdf",
                files={"file": ("sales.csv", SAMPLE, "text/csv")},
            ).status_code
            for _ in range(6)
        ]
    finally:
        semaphore.release()

    assert statuses == [503, 503, 503, 503, 503, 429]


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


def test_pdf_diagnostic_logs_are_structured_and_exclude_input(
    client: TestClient, monkeypatch, caplog
) -> None:
    private_values = (
        "PRIVATE_FILE_NAME.csv",
        "PRIVATE_PRODUCT",
        "PRIVATE_CATEGORY",
        "PRIVATE_REGION",
        "PRIVATE_CUSTOMER",
        "PRIVATE_EXCEPTION",
    )

    def failed(report):
        raise PdfReportError(PdfErrorCode.RENDER_FAILED) from RuntimeError(
            private_values[-1]
        )

    monkeypatch.setattr("app.web.routes.pdf_report_renderer.render_pdf", failed)
    data = (
        b"date,product,category,region,quantity,unit_price,customer_type\n"
        b"2026-01-01,PRIVATE_PRODUCT,PRIVATE_CATEGORY,PRIVATE_REGION,1,10,PRIVATE_CUSTOMER\n"
    )
    logger_name = "uvicorn.error.equa_analytics.pdf"
    with caplog.at_level(logging.INFO, logger=logger_name):
        response = client.post(
            "/reports/pdf",
            files={"file": (private_values[0], data, "text/csv")},
        )

    assert response.status_code == 500
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == logger_name
    ]
    events = [json.loads(message) for message in messages]
    assert [event["event"] for event in events] == [
        "pdf_slot_attempt",
        "pdf_slot_acquired",
        "pdf_render_start",
        "pdf_render_failed",
        "pdf_slot_released",
    ]
    assert len({event["request_id"] for event in events}) == 1
    assert all("process_id" in event and "elapsed_ms" in event for event in events)
    serialized = "".join(messages)
    for forbidden in private_values:
        assert forbidden not in serialized
    assert "filename" not in serialized.lower()
    assert "raw" not in serialized.lower()


def test_dashboard_keeps_html_and_adds_pdf_download(client: TestClient) -> None:
    response = client.post(
        "/dashboard", files={"file": ("sales.csv", SAMPLE, "text/csv")}
    )

    assert response.status_code == 200
    assert 'action="/reports/html"' in response.text
    assert 'action="/reports/pdf"' in response.text
    assert "Download HTML Report" in response.text
    assert "Download PDF Report" in response.text
    assert "data-pdf-form" in response.text
    assert "data-pdf-submit" in response.text

    script = client.get("/static/js/app.js").text
    assert 'form.dataset.submitting === "true"' in script
    assert "button.disabled = true" in script
    assert "resetPdfForm(form)" in script
    assert "window.setTimeout" in script
    assert 'window.addEventListener("pageshow"' in script
