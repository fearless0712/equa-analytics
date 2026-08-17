import csv
from io import StringIO
from pathlib import Path

from fastapi.testclient import TestClient


def test_home_has_accessible_upload_form_and_security_headers(
    client: TestClient,
) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'action="/dashboard"' in response.text
    assert 'method="post"' in response.text
    assert 'for="csv-file"' in response.text
    assert 'id="csv-file"' in response.text
    assert 'aria-busy="false"' in response.text
    assert "Analyze Data" in response.text
    assert "Maximum 5 MB" in response.text
    assert "Maximum 10,000 rows" in response.text
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_valid_sample_renders_complete_dashboard(client: TestClient) -> None:
    sample = Path("sample_data/valid_sales.csv").read_bytes()
    response = client.post(
        "/dashboard",
        files={"file": ("sales.csv", sample, "text/csv")},
    )

    assert response.status_code == 200
    for text in (
        "Performance Dashboard",
        "Data Quality",
        "Key Metrics",
        "Total Sales",
        "Monthly Performance",
        "Product Performance",
        "Category Performance",
        "Regional Performance",
        "Detected Insights",
        "Calculated deterministically from uploaded data.",
        "AI Insights",
        "AI interprets calculated results. It does not calculate KPIs",
    ):
        assert text in response.text
    assert "Duplicate rows are detected and retained" in response.text
    assert "Date Range" in response.text
    assert "Observed Months" in response.text
    assert "Imputed Months" in response.text
    assert "Potential Outliers" in response.text
    assert "Business Signals" in response.text
    assert "Data Quality Signals" in response.text
    assert response.text.count("data-chart-spec=") == 5
    assert "/static/vendor/plotly.min.js" in response.text


def test_dashboard_get_redirects_to_upload_without_404(
    client: TestClient,
) -> None:
    response = client.get("/dashboard", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_dashboard_post_renders_directly_without_redirect(
    client: TestClient,
) -> None:
    sample = Path("sample_data/valid_sales.csv").read_bytes()
    response = client.post(
        "/dashboard",
        files={"file": ("sales.csv", sample, "text/csv")},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Performance Dashboard" in response.text
    assert "location" not in response.headers


def test_dashboard_renders_safe_validation_errors(client: TestClient) -> None:
    data = b"date,product\nPRIVATE_CSV_BODY,value\n"
    response = client.post(
        "/dashboard",
        files={"file": ("sales.csv", data, "text/csv")},
    )

    assert response.status_code == 422
    assert "CSV validation failed" in response.text
    assert "CSV_MISSING_REQUIRED_COLUMN" in response.text
    assert "PRIVATE_CSV_BODY" not in response.text
    assert "Traceback" not in response.text


def test_dashboard_escapes_user_names_in_tables_and_chart_transport(
    client: TestClient,
) -> None:
    product = "<script>alert(1)</script>"
    category = "<img src=x onerror=alert(1)>"
    region = '\"><svg onload=alert(1)>'
    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(
        ["date", "product", "category", "region", "quantity", "unit_price"]
    )
    writer.writerow(["2026-01-01", product, category, region, "1", "10"])

    response = client.post(
        "/dashboard",
        files={"file": ("sales.csv", stream.getvalue().encode(), "text/csv")},
    )

    assert response.status_code == 200
    assert product not in response.text
    assert category not in response.text
    assert region not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "&lt;img src=x onerror=alert(1)&gt;" in response.text
    assert "&lt;svg onload=alert(1)&gt;" in response.text
    assert "data-chart-spec=" in response.text


def test_detected_insight_summary_escapes_xss_dimension_value(
    client: TestClient,
) -> None:
    product = "<script>alert(1)</script>"
    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(
        ["date", "product", "category", "region", "quantity", "unit_price"]
    )
    writer.writerow(["2026-01-01", product, "Office", "North", "0", "10"])

    response = client.post(
        "/dashboard",
        files={"file": ("sales.csv", stream.getvalue().encode(), "text/csv")},
    )

    assert response.status_code == 200
    assert product not in response.text
    assert "The product &lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "OPENAI_API_KEY" not in response.text
    assert "Traceback" not in response.text


def test_static_assets_include_responsive_and_submit_safeguards(
    client: TestClient,
) -> None:
    css = client.get("/static/css/app.css")
    javascript = client.get("/static/js/app.js")
    plotly = client.get("/static/vendor/plotly.min.js")

    assert css.status_code == javascript.status_code == plotly.status_code == 200
    assert "@media (max-width: 760px)" in css.text
    assert "overflow-x: auto" in css.text
    assert ":focus-visible" in css.text
    assert 'form.dataset.submitting === "true"' in javascript.text
    assert 'form.setAttribute("aria-busy", "true")' in javascript.text
    assert 'window.addEventListener("pageshow"' in javascript.text
    assert len(plotly.content) > 1_000_000
