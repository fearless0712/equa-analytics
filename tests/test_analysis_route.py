from fastapi.testclient import TestClient

from app.config import Environment, Settings
from app.main import create_app

ANALYSIS_CSV = (
    b"date,product,category,region,quantity,unit_price,discount,customer_type\n"
    b"2026-01-03,Alpha,Office,North,1,1.1,0,PRIVATE_TYPE\n"
    b"2026-02-04,Beta,Home,South,2,1.1,0,PRIVATE_TYPE\n"
)


def test_analysis_route_returns_exact_kpis_and_aggregates(client: TestClient) -> None:
    response = client.post(
        "/csv/analyze",
        files={"file": ("sales.csv", ANALYSIS_CSV, "text/csv")},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["kpis"]["total_sales"] == "3.3"
    assert body["kpis"]["total_quantity"] == 3
    assert body["kpis"]["transaction_count"] == 2
    assert body["monthly"][1]["sales_change"] == "1.1"
    assert body["top_products"][0]["name"] == "Beta"
    assert body["quality"]["total_rows"] == 2
    assert body["quality"]["duplicate_rows"] == 0
    assert "PRIVATE_TYPE" not in response.text
    assert "2026-01-03" not in response.text


def test_analysis_route_returns_safe_validation_error(client: TestClient) -> None:
    private_content = "PRIVATE_BROKEN_CONTENT"
    data = (
        b"date,product,category,region,quantity,unit_price\n"
        + f'2026-01-03,"{private_content},Office,North,1,10\n'.encode()
    )
    response = client.post(
        "/csv/analyze",
        files={"file": ("sales.csv", data, "text/csv")},
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "CSV_PARSE_ERROR"
    assert private_content not in response.text
    assert "Traceback" not in response.text


def test_analysis_route_escapes_xss_names_in_json_transport(client: TestClient) -> None:
    xss = "<script>alert(1)</script>"
    data = ANALYSIS_CSV.replace(b"Alpha", xss.encode())
    response = client.post(
        "/csv/analyze",
        files={"file": ("sales.csv", data, "text/csv")},
    )

    assert response.status_code == 200
    assert xss not in response.text
    assert "\\u003cscript\\u003e" in response.text
    assert response.json()["products"][1]["name"] == xss
    assert response.headers["content-type"].startswith("application/json")


def test_analysis_route_does_not_expose_internal_exception(monkeypatch) -> None:
    def fail_safely(*args, **kwargs):
        raise RuntimeError("PRIVATE_INTERNAL_EXCEPTION")

    monkeypatch.setattr("app.web.routes.analyze_rows", fail_safely)
    settings = Settings(environment=Environment.TEST, debug=False)
    with TestClient(
        create_app(settings), raise_server_exceptions=False
    ) as isolated_client:
        isolated_client.get("/")
        isolated_client.headers["X-CSRF-Token"] = isolated_client.cookies["equa_csrf"]
        response = isolated_client.post(
            "/csv/analyze",
            files={"file": ("sales.csv", ANALYSIS_CSV, "text/csv")},
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "PRIVATE_INTERNAL_EXCEPTION" not in response.text
    assert "Traceback" not in response.text
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
