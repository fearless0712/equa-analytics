import pytest
from pydantic import ValidationError

from app.config import Environment, Settings


def test_production_rejects_debug() -> None:
    with pytest.raises(ValidationError, match="Debug mode must be disabled"):
        Settings(environment=Environment.PRODUCTION, debug=True, secret_key="a-secure-key")


def test_production_requires_secret_key() -> None:
    with pytest.raises(ValidationError, match="secret key is required"):
        Settings(environment=Environment.PRODUCTION, secret_key="")


def test_production_rejects_example_secret_key() -> None:
    with pytest.raises(ValidationError, match="example secret key"):
        Settings(
            environment=Environment.PRODUCTION,
            secret_key="change-me-before-production",
        )


def test_production_requires_explicit_permission_for_fake_ai() -> None:
    with pytest.raises(ValidationError, match="Fake AI requires explicit permission"):
        Settings(
            environment=Environment.PRODUCTION,
            secret_key="test-only-production-secret",
            ai_mode="fake",
        )

    settings = Settings(
        environment=Environment.PRODUCTION,
        secret_key="test-only-production-secret",
        ai_mode="fake",
        allow_fake_ai_in_production=True,
    )
    assert settings.ai_mode.value == "fake"


def test_development_uses_safe_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment is Environment.DEVELOPMENT
    assert settings.debug is False
    assert settings.ai_mode.value == "disabled"
    assert settings.openai_api_key.get_secret_value() == ""
    assert settings.openai_timeout_seconds == 20.0
    assert settings.openai_max_retries == 2
