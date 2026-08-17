from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class AiMode(StrEnum):
    DISABLED = "disabled"
    FAKE = "fake"
    OPENAI = "openai"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        populate_by_name=True,
    )

    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        validation_alias="EQUA_ANALYTICS_ENV",
    )
    debug: bool = Field(
        default=False,
        validation_alias="EQUA_ANALYTICS_DEBUG",
    )
    secret_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="EQUA_ANALYTICS_SECRET_KEY",
    )
    ai_mode: AiMode = Field(
        default=AiMode.DISABLED,
        validation_alias="AI_MODE",
    )
    allow_fake_ai_in_production: bool = Field(
        default=False,
        validation_alias="ALLOW_FAKE_AI_IN_PRODUCTION",
    )
    openai_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="OPENAI_API_KEY",
    )
    openai_model: str = Field(
        default="",
        validation_alias="OPENAI_MODEL",
    )
    openai_timeout_seconds: float = Field(
        default=20.0,
        gt=0,
        le=120,
        validation_alias="OPENAI_TIMEOUT_SECONDS",
    )
    openai_max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        validation_alias="OPENAI_MAX_RETRIES",
    )
    max_csv_file_size: int = Field(
        default=5 * 1024 * 1024,
        gt=0,
        validation_alias="MAX_CSV_FILE_SIZE",
    )
    max_csv_rows: int = Field(
        default=10_000,
        gt=0,
        validation_alias="MAX_CSV_ROWS",
    )

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.environment is not Environment.PRODUCTION:
            return self
        if self.debug:
            raise ValueError("Debug mode must be disabled in production")
        secret_key = self.secret_key.get_secret_value()
        if not secret_key.strip():
            raise ValueError("A secret key is required in production")
        if secret_key == "change-me-before-production":
            raise ValueError("The example secret key cannot be used in production")
        if self.ai_mode is AiMode.FAKE and not self.allow_fake_ai_in_production:
            raise ValueError("Fake AI requires explicit permission in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
