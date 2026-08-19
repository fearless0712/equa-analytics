from pathlib import Path
import re

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]


def test_python_declarations_are_pinned_and_compatible() -> None:
    declared = (ROOT / ".python-version").read_text().strip()
    dockerfile = (ROOT / "Dockerfile").read_text()
    pyproject = (ROOT / "pyproject.toml").read_text()

    assert re.fullmatch(r"3\.12\.\d+", declared)
    assert f"FROM python:{declared}-slim-bookworm" in dockerfile
    assert 'requires-python = ">=3.12,<3.13"' in pyproject


def test_docker_runtime_is_non_root_single_worker_and_has_pdf_libraries() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()

    for package in (
        "fontconfig",
        "fonts-dejavu-core",
        "libharfbuzz-subset0",
        "libpango-1.0-0",
        "libpangoft2-1.0-0",
    ):
        assert package in dockerfile
    assert "USER equa" in dockerfile
    assert "--workers 1" in dockerfile
    assert "${PORT:-10000}" in dockerfile
    assert "HEALTHCHECK" in dockerfile


def test_render_blueprint_uses_docker_health_check_and_no_secret_literals() -> None:
    blueprint = (ROOT / "render.yaml").read_text()

    assert "runtime: docker" in blueprint
    assert "healthCheckPath: /health" in blueprint
    assert "autoDeploy: false" in blueprint
    assert "value: production" in blueprint
    assert "value: disabled" in blueprint
    for secret in ("EQUA_ANALYTICS_SECRET_KEY", "OPENAI_API_KEY"):
        block = blueprint.split(f"- key: {secret}", 1)[1].split("- key:", 1)[0]
        assert "sync: false" in block
        assert "value:" not in block


def test_docker_context_excludes_local_secrets_and_credentials() -> None:
    ignored = (ROOT / ".dockerignore").read_text().splitlines()

    assert ".git" in ignored
    assert ".venv" in ignored
    assert ".env" in ignored
    assert ".env.*" in ignored
    assert "!.env.example" in ignored
    assert "*.html" not in ignored


def test_production_health_route_is_lightweight(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_production_smoke_is_deterministic_and_never_uses_ai() -> None:
    smoke = (ROOT / "scripts" / "production_smoke.py").read_text()

    assert "PdfReportRenderer().render_pdf(report)" in smoke
    assert 'pdf.startswith(b"%PDF-")' in smoke
    assert "build_ai_provider" not in smoke
    assert "OpenAiProvider" not in smoke
