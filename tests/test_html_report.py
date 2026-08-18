import csv
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from fastapi.testclient import TestClient

from app.ai.context_builder import build_ai_context
from app.ai.fake_ai import FakeAiProvider
from app.presentation.html_report_renderer import HtmlReportRenderer
from app.services.report_builder import build_business_report
from tests.test_ai_context import _results

SAMPLE = Path("sample_data/valid_sales.csv").read_bytes()
GENERATED_AT = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)


def _report(*, with_ai: bool = False, ai_unavailable: bool = False):
    analysis, insights = _results()
    ai = FakeAiProvider().generate(build_ai_context(analysis, insights)) if with_ai else None
    return build_business_report(
        analysis,
        insights,
        ai=ai,
        ai_unavailable=ai_unavailable,
        generated_at=GENERATED_AT,
    )


def test_renderer_builds_self_contained_printable_report() -> None:
    html = HtmlReportRenderer().render(_report())

    for title in (
        "01</span><h2>Executive Summary",
        "02</span><h2>Key Performance Indicators",
        "03</span><h2>Monthly Performance",
        "04</span><h2>Product Performance",
        "05</span><h2>Category Performance",
        "06</span><h2>Regional Performance",
        "07</span><h2>Detected Insights",
        "08</span><h2>AI Analysis",
        "09</span><h2>Recommended Actions",
        "10</span><h2>Data Quality &amp; Methodology",
    ):
        assert title in html
    assert "@page" in html
    assert "/*__EQUA_REPORT_CSS__*/" not in html
    assert "<script" not in html.lower()
    assert "<link" not in html.lower()
    assert "http://" not in html.lower()
    assert "https://" not in html.lower()
    assert "plotly" not in html.lower()
    assert "data-chart-spec" not in html.lower()


def test_renderer_uses_presentation_formatters_and_comparison_fallback() -> None:
    report = _report()
    precise = report.model_copy(
        update={
            "kpis": report.kpis.model_copy(
                update={"average_order_value": "2857.941176470588235294117647"}
            )
        }
    )

    html = HtmlReportRenderer().render(precise)

    assert "2,857.94" in html
    assert "2857.941176470588235294117647" not in html
    assert "N/A" in html


def test_renderer_formats_deterministic_evidence_without_losing_precision() -> None:
    report = _report()
    raw_one = "30.436348667284141195842338170"
    raw_three = "81.85139446331172172481218483"
    source = report.insights.business[0]
    concentration = source.model_copy(
        update={
            "id": "presentation-concentration",
            "evidence": (
                f"top_one_share={raw_one}",
                f"top_three_share={raw_three}",
                "significant=true",
                "optional=None",
            ),
        }
    )
    outlier = source.model_copy(
        update={
            "id": "presentation-outlier",
            "evidence": ("lower_bound=-4.000", "upper_bound=28237.500"),
        }
    )
    report = report.model_copy(
        update={
            "insights": report.insights.model_copy(
                update={"business": (concentration,), "outliers": (outlier,)}
            )
        }
    )

    html = HtmlReportRenderer().render(report)

    assert "Leading share: 30.44%" in html
    assert "Top three share: 81.85%" in html
    assert "Significant: true" in html
    assert "Optional: N/A" in html
    assert "Lower bound: -4" in html
    assert "Upper bound: 28,237.50" in html
    assert raw_one not in html
    assert raw_three not in html
    assert '<div class="evidence"><strong>Evidence</strong><ul>' in html


def test_renderer_has_explicit_ai_states_and_includes_existing_ai() -> None:
    plain = HtmlReportRenderer().render(_report())
    unavailable = HtmlReportRenderer().render(_report(ai_unavailable=True))
    included = HtmlReportRenderer().render(_report(with_ai=True))

    assert "AI interpretation was not requested" in plain
    assert "AI interpretation was unavailable" in unavailable
    assert "Key Findings" in included
    assert "Recommended Actions" in included


def test_renderer_escapes_aggregates_insights_and_ai_text() -> None:
    report = _report(with_ai=True)
    attack = "</style><script>alert(1)</script>"
    product = report.top_products[0].model_copy(update={"name": attack})
    insight = report.insights.business[0].model_copy(
        update={"title": attack, "summary": attack, "evidence": (f"note={attack}",)}
    )
    finding = report.ai.key_findings[0].model_copy(
        update={"title": attack, "observation": attack, "evidence": attack}
    )
    report = report.model_copy(
        update={
            "top_products": (product,),
            "insights": report.insights.model_copy(update={"business": (insight,)}),
            "ai": report.ai.model_copy(
                update={"executive_summary": attack, "key_findings": (finding,)}
            ),
        }
    )

    html = HtmlReportRenderer().render(report)

    assert attack not in html
    assert "&lt;/style&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "Note: &lt;/style&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert html.lower().count("<script") == 0


def test_report_print_css_ends_on_white_page_without_empty_footer_block() -> None:
    css = Path("app/static/css/report.css").read_text()
    template = Path("app/templates/reports/business_report.html").read_text()

    assert "@page { size: A4; margin: 14mm; background: #fff; }" in css
    assert ":root, html, body { background: #fff; }" in css
    assert ".report-footer { background: #fff; padding-bottom: 0; }" in css
    assert "</footer>\n</main>" in template
    assert "min-height" not in css
    assert "::after" not in css


def test_report_download_route_returns_safe_attachment(client: TestClient) -> None:
    response = client.post(
        "/reports/html",
        files={"file": ("confidential-client-name.csv", SAMPLE, "text/csv")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="equa-analytics-report-'
    )
    assert response.headers["content-disposition"].endswith('.html"')
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "Business Performance Report" in response.text
    assert "confidential-client-name" not in response.text
    assert "OPENAI_API_KEY" not in response.text
    assert "raw_rows" not in response.text


def test_report_route_rejects_invalid_csv_without_content_exposure(
    client: TestClient,
) -> None:
    private_value = "PRIVATE_ROW_VALUE"
    response = client.post(
        "/reports/html",
        files={"file": ("sales.csv", f"date,product\n2026-01-01,{private_value}\n".encode(), "text/csv")},
    )

    assert response.status_code == 422
    assert "CSV_MISSING_REQUIRED_COLUMN" in response.text
    assert private_value not in response.text
    assert "Traceback" not in response.text


def test_report_route_escapes_xss_and_excludes_customer_detail(
    client: TestClient,
) -> None:
    product_attack = "<script>alert(1)</script>"
    category_attack = "<img src=x onerror=alert(1)>"
    region_attack = "</style><script>alert(2)</script>"
    secret_detail = "CONFIDENTIAL_CUSTOMER_DETAIL"
    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(
        ["date", "product", "category", "region", "quantity", "unit_price", "customer_type"]
    )
    writer.writerow(
        [
            "2026-01-01",
            product_attack,
            category_attack,
            region_attack,
            "1",
            "10",
            secret_detail,
        ]
    )

    response = client.post(
        "/reports/html",
        files={"file": ("sales.csv", stream.getvalue().encode(), "text/csv")},
    )

    assert response.status_code == 200
    assert product_attack not in response.text
    assert category_attack not in response.text
    assert region_attack not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "&lt;img src=x onerror=alert(1)&gt;" in response.text
    assert "&lt;/style&gt;&lt;script&gt;alert(2)&lt;/script&gt;" in response.text
    assert secret_detail not in response.text
    assert "AI context" not in response.text
    assert "prompt" not in response.text.lower()
    assert response.text.lower().count("<script") == 0


def test_report_route_enforces_rendered_size_limit(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.presentation.html_report_renderer.MAX_HTML_REPORT_BYTES", 1
    )

    response = client.post(
        "/reports/html", files={"file": ("sales.csv", SAMPLE, "text/csv")}
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "HTML report exceeds the safe size limit."}
    assert "EQUA ANALYTICS" not in response.text


def test_dashboard_exposes_report_download_form(client: TestClient) -> None:
    response = client.post(
        "/dashboard", files={"file": ("sales.csv", SAMPLE, "text/csv")}
    )

    assert response.status_code == 200
    assert 'action="/reports/html"' in response.text
    assert "Download HTML Report" in response.text
