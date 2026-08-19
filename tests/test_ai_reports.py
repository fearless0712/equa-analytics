from pathlib import Path
import re

from fastapi.testclient import TestClient

from app.ai.fake_ai import FakeAiProvider
from app.ai.models import AiInsightResponse, AiServiceError, AiErrorCode
from app.config import AiMode, Environment, Settings
from app.main import create_app
from app.presentation.pdf_report_renderer import PdfErrorCode, PdfReportError

SAMPLE = Path("sample_data/valid_sales.csv").read_bytes()


def _client(mode: AiMode = AiMode.FAKE) -> TestClient:
    client = TestClient(
        create_app(Settings(environment=Environment.TEST, ai_mode=mode))
    )
    client.__enter__()
    client.get("/")
    client.headers["X-CSRF-Token"] = client.cookies["equa_csrf"]
    return client


class CountingProvider:
    def __init__(self, *, error: AiServiceError | None = None) -> None:
        self.calls = 0
        self.error = error
        self.fake = FakeAiProvider()

    def generate(self, context) -> AiInsightResponse:
        self.calls += 1
        if self.error:
            raise self.error
        return self.fake.generate(context)


def test_ai_html_report_includes_fake_ai_once(monkeypatch) -> None:
    provider = CountingProvider()
    monkeypatch.setattr("app.web.routes.build_ai_provider", lambda settings: provider)

    with _client() as client:
        response = client.post(
            "/reports/html/ai",
            files={"file": ("private-name.csv", SAMPLE, "text/csv")},
        )

    assert response.status_code == 200
    assert provider.calls == 1
    assert "AI Analysis" in response.text
    assert "Executive Interpretation" in response.text
    assert "Recommended Actions" in response.text


def test_fake_ai_html_report_has_no_high_precision_decimal_text() -> None:
    with _client() as client:
        response = client.post(
            "/reports/html/ai",
            files={"file": ("sales.csv", SAMPLE, "text/csv")},
        )

    assert response.status_code == 200
    assert not re.findall(r"-?\d+\.\d{6,}", response.text)
    assert "30.44%" in response.text
    assert "-6.83%" in response.text
    assert "Next Questions" in response.text
    assert "private-name.csv" not in response.text
    assert "AI interpretation was unavailable" not in response.text


def test_openai_mode_ai_report_uses_mock_provider_once(monkeypatch) -> None:
    provider = CountingProvider()
    monkeypatch.setattr("app.web.routes.build_ai_provider", lambda settings: provider)

    with _client(AiMode.OPENAI) as client:
        response = client.post(
            "/reports/html/ai", files={"file": ("sales.csv", SAMPLE, "text/csv")}
        )

    assert response.status_code == 200
    assert provider.calls == 1
    assert "Executive Interpretation" in response.text


def test_ai_html_report_falls_back_when_provider_fails(monkeypatch) -> None:
    provider = CountingProvider(error=AiServiceError(AiErrorCode.TIMEOUT))
    monkeypatch.setattr("app.web.routes.build_ai_provider", lambda settings: provider)

    with _client() as client:
        response = client.post(
            "/reports/html/ai", files={"file": ("sales.csv", SAMPLE, "text/csv")}
        )

    assert response.status_code == 200
    assert provider.calls == 1
    assert "AI interpretation was unavailable" in response.text
    assert "AI_TIMEOUT" not in response.text
    assert "Business Performance Report" in response.text


def test_ai_pdf_report_includes_ai_once_and_releases_slot(monkeypatch) -> None:
    provider = CountingProvider()
    captured = {}
    monkeypatch.setattr("app.web.routes.build_ai_provider", lambda settings: provider)

    def render(report):
        captured["report"] = report
        return b"%PDF-ai"

    monkeypatch.setattr("app.web.routes.pdf_report_renderer.render_pdf", render)
    with _client() as client:
        response = client.post(
            "/reports/pdf/ai", files={"file": ("sales.csv", SAMPLE, "text/csv")}
        )
        assert client.app.state.pdf_semaphore.locked() is False

    assert response.status_code == 200
    assert response.content == b"%PDF-ai"
    assert provider.calls == 1
    assert captured["report"].ai_status.value == "included"
    assert captured["report"].ai is not None
    assert len(captured["report"].ai.recommendations) <= 5
    assert len(captured["report"].ai.optional_next_questions) <= 3


def test_ai_pdf_provider_failure_still_generates_deterministic_pdf(monkeypatch) -> None:
    provider = CountingProvider(error=AiServiceError(AiErrorCode.PROVIDER_ERROR))
    captured = {}
    monkeypatch.setattr("app.web.routes.build_ai_provider", lambda settings: provider)

    def render(report):
        captured["report"] = report
        return b"%PDF-fallback"

    monkeypatch.setattr("app.web.routes.pdf_report_renderer.render_pdf", render)
    with _client() as client:
        response = client.post(
            "/reports/pdf/ai", files={"file": ("sales.csv", SAMPLE, "text/csv")}
        )
        assert client.app.state.pdf_semaphore.locked() is False

    assert response.status_code == 200
    assert provider.calls == 1
    assert captured["report"].ai_status.value == "unavailable"


def test_ai_pdf_renderer_error_releases_slot(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.web.routes.pdf_report_renderer.render_pdf",
        lambda report: (_ for _ in ()).throw(
            PdfReportError(PdfErrorCode.RENDER_FAILED)
        ),
    )
    with _client() as client:
        response = client.post(
            "/reports/pdf/ai", files={"file": ("sales.csv", SAMPLE, "text/csv")}
        )
        assert client.app.state.pdf_semaphore.locked() is False

    assert response.status_code == 500
    assert response.json()["code"] == "PDF_RENDER_FAILED"


def test_ai_pdf_uses_existing_pdf_concurrency_slot(monkeypatch) -> None:
    monkeypatch.setattr("app.web.routes.PDF_SLOT_TIMEOUT_SECONDS", 0.01)
    provider = CountingProvider()
    monkeypatch.setattr("app.web.routes.build_ai_provider", lambda settings: provider)

    with _client() as client:
        semaphore = client.app.state.pdf_semaphore
        import asyncio

        asyncio.run(semaphore.acquire())
        try:
            response = client.post(
                "/reports/pdf/ai",
                files={"file": ("sales.csv", SAMPLE, "text/csv")},
            )
        finally:
            semaphore.release()

    assert response.status_code == 503
    assert response.json()["code"] == "PDF_BUSY"
    assert provider.calls == 1


def test_ai_report_rate_limit_falls_back_without_extra_provider_call(monkeypatch) -> None:
    provider = CountingProvider()
    monkeypatch.setattr("app.web.routes.build_ai_provider", lambda settings: provider)

    with _client() as client:
        responses = [
            client.post(
                "/reports/html/ai",
                files={"file": ("sales.csv", SAMPLE, "text/csv")},
            )
            for _ in range(4)
        ]

    assert [response.status_code for response in responses] == [200, 200, 200, 200]
    assert provider.calls == 3
    assert "AI interpretation was unavailable" in responses[-1].text


def test_ai_pdf_applies_pdf_rate_limit_as_well_as_ai_limit(monkeypatch) -> None:
    provider = CountingProvider()
    monkeypatch.setattr("app.web.routes.build_ai_provider", lambda settings: provider)
    monkeypatch.setattr(
        "app.web.routes.pdf_report_renderer.render_pdf", lambda report: b"%PDF-test"
    )

    with _client() as client:
        responses = [
            client.post(
                "/reports/pdf/ai",
                files={"file": ("sales.csv", SAMPLE, "text/csv")},
            )
            for _ in range(6)
        ]

    assert [response.status_code for response in responses] == [200] * 5 + [429]
    assert responses[-1].json()["code"] == "PDF_RATE_LIMITED"
    assert provider.calls == 3


def test_ai_report_escapes_ai_output_and_formats_evidence(monkeypatch) -> None:
    attack = "</style><script>alert(1)</script> ignore previous instructions"
    fake = FakeAiProvider()

    class UntrustedProvider:
        def generate(self, context):
            response = fake.generate(context)
            finding = response.key_findings[0].model_copy(
                update={
                    "evidence": (
                        "monthly[2026-04].sales_change_pct = "
                        "-12.514370175726720315322713089; "
                        "regions[North].sales_share = "
                        "30.436348667284141195842338170217; severity warning."
                    )
                }
            )
            recommendation = response.recommendations[0].model_copy(
                update={
                    "title": attack,
                    "evidence": (
                        "Desk Chair is reported as a leading product with "
                        "sales_share of 27.606257075228980...",
                        "Office sales 32750 versus 35150.00 previously",
                    ),
                }
            )
            return response.model_copy(
                update={
                    "executive_summary": attack,
                    "key_findings": (finding,),
                    "recommendations": (recommendation,),
                }
            )

    monkeypatch.setattr(
        "app.web.routes.build_ai_provider", lambda settings: UntrustedProvider()
    )
    with _client() as client:
        response = client.post(
            "/reports/html/ai",
            files={"file": ("SECRET_FILENAME.csv", SAMPLE, "text/csv")},
        )

    assert response.status_code == 200
    assert attack not in response.text
    assert "&lt;/style&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "Sales change: -12.51%" in response.text
    assert "North sales share: 30.44%" in response.text
    assert (
        "Desk Chair is reported as a leading product with sales share: 27.61%"
        in response.text
    )
    assert "Office sales 32,750 versus 35,150 previously" in response.text
    assert "30.436348667284141195842338170217" not in response.text
    assert "-12.514370175726720315322713089" not in response.text
    assert "27.606257075228980" not in response.text
    assert "SECRET_FILENAME" not in response.text
    assert response.text.lower().count("<script") == 0


def test_dashboard_exposes_optional_ai_report_control() -> None:
    with _client() as client:
        response = client.post(
            "/dashboard", files={"file": ("sales.csv", SAMPLE, "text/csv")}
        )

    assert 'id="report-include-ai"' in response.text
    assert 'role="switch"' in response.text
    assert "Include AI interpretation" in response.text
    assert "Uses deterministic analysis only." in response.text
