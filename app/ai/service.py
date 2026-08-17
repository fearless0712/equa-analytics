from app.ai.base import AiProvider
from app.ai.fake_ai import FakeAiProvider
from app.ai.models import AiErrorCode, AiServiceError
from app.ai.openai_ai import OpenAiProvider
from app.config import AiMode, Settings


def build_ai_provider(settings: Settings) -> AiProvider:
    if settings.ai_mode is AiMode.DISABLED:
        raise AiServiceError(AiErrorCode.DISABLED)
    if settings.ai_mode is AiMode.FAKE:
        return FakeAiProvider()
    api_key = settings.openai_api_key.get_secret_value().strip()
    model = settings.openai_model.strip()
    if not api_key or not model:
        raise AiServiceError(AiErrorCode.CONFIGURATION_ERROR)
    return OpenAiProvider(
        api_key=api_key,
        model=model,
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )
