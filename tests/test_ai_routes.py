from pathlib import Path

from fastapi.testclient import TestClient

from app.ai.fake_ai import FakeAiProvider
from app.config import AiMode, Environment, Settings
from app.main import create_app

SAMPLE = Path("sample_data/valid_sales.csv").read_bytes()


def _client(mode: AiMode) -> TestClient:
    client = TestClient(create_app(Settings(environment=Environment.TEST, ai_mode=mode)))
    client.__enter__()
    client.get("/")
    client.headers["X-CSRF-Token"] = client.cookies["equa_csrf"]
    return client


def test_ai_fake_route_reruns_pipeline_and_renders_result() -> None:
    with _client(AiMode.FAKE) as client:
        response = client.post("/ai/insights", files={"file": ("sales.csv", SAMPLE, "text/csv")})
    assert response.status_code == 200
    assert "Executive Summary" in response.text
    assert "Recommended Actions" in response.text
    assert "Next Questions" in response.text
    assert "priority-high" in response.text or "priority-medium" in response.text
    assert "Generate AI Insights" in response.text
    assert "Traceback" not in response.text


def test_ai_disabled_is_safe_and_dashboard_remains_visible() -> None:
    with _client(AiMode.DISABLED) as client:
        response = client.post("/ai/insights", files={"file": ("sales.csv", SAMPLE, "text/csv")})
    assert response.status_code == 503
    assert "AI_DISABLED" in response.text
    assert "Performance Dashboard" in response.text


def test_all_post_routes_reject_missing_or_invalid_csrf() -> None:
    with TestClient(create_app(Settings(environment=Environment.TEST))) as client:
        for path in ("/csv/validate", "/csv/analyze", "/dashboard", "/ai/insights", "/reports/html", "/reports/pdf"):
            response = client.post(path, files={"file": ("sales.csv", SAMPLE, "text/csv")})
            assert response.status_code == 403
        client.get("/")
        client.headers["X-CSRF-Token"] = "invalid"
        assert client.post("/csv/validate", files={"file": ("sales.csv", SAMPLE, "text/csv")}).status_code == 403


def test_ai_route_rate_limit_is_three_requests_per_ten_minutes() -> None:
    with _client(AiMode.FAKE) as client:
        statuses = [client.post("/ai/insights", headers={"X-Forwarded-For": f"198.51.100.{index}"}, files={"file": ("sales.csv", SAMPLE, "text/csv")}).status_code for index in range(4)]
    assert statuses == [200, 200, 200, 429]


def test_openai_mode_route_can_be_mocked_without_external_call(monkeypatch) -> None:
    provider = FakeAiProvider()
    monkeypatch.setattr("app.web.routes.build_ai_provider", lambda settings: provider)
    with _client(AiMode.OPENAI) as client:
        response = client.post("/ai/insights", files={"file": ("sales.csv", SAMPLE, "text/csv")})
    assert response.status_code == 200
    assert "Executive Summary" in response.text


def test_ai_ui_has_loading_and_double_submit_protection(client: TestClient) -> None:
    dashboard = client.post("/dashboard", files={"file": ("sales.csv", SAMPLE, "text/csv")})
    script = client.get("/static/js/ai_insights.js")
    assert "AI interprets calculated results" in dashboard.text
    assert 'action="/ai/insights"' in dashboard.text
    assert "Generating..." in script.text
    assert 'form.dataset.submitting === "true"' in script.text
    assert "innerHTML" not in script.text


def test_ai_recommendation_output_is_escaped(client: TestClient) -> None:
    xss = "<script>alert(1)</script>"
    data = (
        b"date,product,category,region,quantity,unit_price\n"
        + f"2026-01-01,{xss},Office,North,10,100\n".encode()
        + b"2026-01-02,Beta,Home,South,1,10\n"
        + b"2026-01-03,Gamma,Lifestyle,West,1,10\n"
    )
    with _client(AiMode.FAKE) as fake_client:
        response = fake_client.post(
            "/ai/insights",
            files={"file": ("sales.csv", data, "text/csv")},
        )

    assert response.status_code == 200
    assert xss not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text


def test_security_headers_include_no_store_permissions_and_production_hsts() -> None:
    with TestClient(create_app(Settings(environment=Environment.PRODUCTION, secret_key="test-only-production-secret"))) as client:
        response = client.get("/")
    assert response.headers["cache-control"] == "no-store"
    assert "camera=()" in response.headers["permissions-policy"]
    assert "max-age=" in response.headers["strict-transport-security"]
    assert "Secure" in response.headers["set-cookie"]
