from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AiImportance(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AiErrorCode(StrEnum):
    DISABLED = "AI_DISABLED"
    CONFIGURATION_ERROR = "AI_CONFIGURATION_ERROR"
    TIMEOUT = "AI_TIMEOUT"
    RATE_LIMITED = "AI_RATE_LIMITED"
    PROVIDER_ERROR = "AI_PROVIDER_ERROR"
    INVALID_RESPONSE = "AI_INVALID_RESPONSE"


class AiFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1, max_length=120)
    observation: str = Field(min_length=1, max_length=400)
    evidence: str = Field(min_length=1, max_length=300)
    importance: AiImportance


class AiInsightResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    executive_summary: str = Field(min_length=1, max_length=600)
    key_findings: tuple[AiFinding, ...] = Field(default=(), max_length=5)
    risks_or_watchpoints: tuple[str, ...] = Field(default=(), max_length=4)
    recommended_checks: tuple[str, ...] = Field(default=(), max_length=4)
    data_quality_note: str | None = Field(default=None, max_length=400)


class AiContextPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    metadata: dict[str, object]
    kpis: dict[str, object]
    monthly: tuple[dict[str, object], ...] = ()
    dimensions: dict[str, tuple[dict[str, object], ...]]
    detected_insights: dict[str, tuple[dict[str, object], ...]]


class AiServiceError(Exception):
    def __init__(self, code: AiErrorCode) -> None:
        self.code = code
        super().__init__(code.value)
