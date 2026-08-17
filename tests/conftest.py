import pytest
from fastapi.testclient import TestClient

from app.config import Environment, Settings
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    settings = Settings(environment=Environment.TEST, debug=False)
    with TestClient(create_app(settings)) as test_client:
        test_client.get("/")
        test_client.headers["X-CSRF-Token"] = test_client.cookies["equa_csrf"]
        yield test_client
