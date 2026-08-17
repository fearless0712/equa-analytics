from fastapi.testclient import TestClient


def test_home_renders_template(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "EQUA Analytics" in response.text
    assert "Data analysis dashboard for business decision-making" in response.text
