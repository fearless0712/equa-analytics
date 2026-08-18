from typing import Any

import openai
from openai import OpenAI

from app.ai.context_builder import serialize_ai_context
from app.ai.models import AiContextPayload, AiErrorCode, AiInsightResponse, AiServiceError
from app.ai.prompts import SYSTEM_PROMPT, build_user_prompt


class OpenAiProvider:
    def __init__(self, *, api_key: str, model: str, timeout: float, max_retries: int, client: Any | None = None) -> None:
        self.model = model
        self.client = client or OpenAI(api_key=api_key, timeout=timeout, max_retries=max_retries)

    def generate(self, context: AiContextPayload) -> AiInsightResponse:
        # Materialize once before the provider call so size constraints are explicit.
        serialize_ai_context(context)
        try:
            response = self.client.responses.parse(
                model=self.model,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(context)},
                ],
                text_format=AiInsightResponse,
                store=False,
                max_output_tokens=1_800,
            )
        except openai.APITimeoutError as exc:
            raise AiServiceError(AiErrorCode.TIMEOUT) from exc
        except openai.RateLimitError as exc:
            raise AiServiceError(AiErrorCode.RATE_LIMITED) from exc
        except openai.AuthenticationError as exc:
            raise AiServiceError(AiErrorCode.CONFIGURATION_ERROR) from exc
        except openai.APIStatusError as exc:
            raise AiServiceError(AiErrorCode.PROVIDER_ERROR) from exc
        except openai.APIError as exc:
            raise AiServiceError(AiErrorCode.PROVIDER_ERROR) from exc

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise AiServiceError(AiErrorCode.INVALID_RESPONSE)
        try:
            return parsed if isinstance(parsed, AiInsightResponse) else AiInsightResponse.model_validate(parsed)
        except ValueError as exc:
            raise AiServiceError(AiErrorCode.INVALID_RESPONSE) from exc
