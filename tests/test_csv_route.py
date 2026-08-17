from fastapi.testclient import TestClient

VALID_CSV = (
    b"date,product,category,region,quantity,unit_price\n"
    b"2026-01-03,Desk Lamp,Office,North,3,4200\n"
)


def test_valid_csv_upload_returns_safe_summary(client: TestClient) -> None:
    response = client.post(
        "/csv/validate",
        files={"file": ("sales.csv", VALID_CSV, "text/csv")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "is_valid": True,
        "errors": [],
        "total_rows": 1,
        "valid_rows": 1,
        "invalid_rows": 0,
        "normalized_headers": [
            "date",
            "product",
            "category",
            "region",
            "quantity",
            "unit_price",
        ],
        "encoding": "utf-8",
    }
    assert "Desk Lamp" not in response.text


def test_invalid_csv_upload_returns_safe_4xx(client: TestClient) -> None:
    private_value = "PRIVATE_CELL_VALUE"
    data = (
        b"date,product,category,region,quantity,unit_price\n"
        + f'2026-01-03,"{private_value},Office,North,3,4200\n'.encode()
    )
    response = client.post(
        "/csv/validate",
        files={"file": ("sales.csv", data, "text/csv")},
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "CSV_PARSE_ERROR"
    assert private_value not in response.text
    assert "Traceback" not in response.text


def test_non_csv_extension_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/csv/validate",
        files={"file": ("sales.txt", VALID_CSV, "text/csv")},
    )

    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "CSV_INVALID_FILE_TYPE"


def test_content_type_is_only_advisory(client: TestClient) -> None:
    response = client.post(
        "/csv/validate",
        files={"file": ("sales.csv", VALID_CSV, "application/octet-stream")},
    )

    assert response.status_code == 200


def test_xss_value_is_not_returned_and_json_is_not_html(client: TestClient) -> None:
    xss = "<script>alert(1)</script>"
    data = VALID_CSV.replace(b"Desk Lamp", xss.encode())
    response = client.post(
        "/csv/validate",
        files={"file": ("sales.csv", data, "text/csv")},
    )

    assert response.status_code == 200
    assert xss not in response.text
    assert response.headers["content-type"].startswith("application/json")


def test_xss_header_is_escaped(client: TestClient) -> None:
    xss = "<script>alert(1)</script>"
    data = VALID_CSV.replace(b"unit_price", xss.encode())
    response = client.post(
        "/csv/validate",
        files={"file": ("sales.csv", data, "text/csv")},
    )

    assert response.status_code == 422
    assert xss not in response.text
    assert "&lt;script&gt;" in response.json()["errors"][1]["field"]


def test_partially_invalid_csv_returns_counts_without_cell_values(
    client: TestClient,
) -> None:
    private_value = "PRIVATE_INVALID_PRODUCT"
    data = VALID_CSV + (
        f"2026-01-04,{private_value},Office,North,-1,4200\n".encode()
    )
    response = client.post(
        "/csv/validate",
        files={"file": ("sales.csv", data, "text/csv")},
    )

    assert response.status_code == 422
    assert response.json()["valid_rows"] == 1
    assert response.json()["invalid_rows"] == 1
    assert response.json()["errors"][0]["code"] == "CSV_NEGATIVE_QUANTITY"
    assert private_value not in response.text
    assert "Traceback" not in response.text
