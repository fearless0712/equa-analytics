from typing import Protocol

from app.ai.models import AiContextPayload, AiInsightResponse


class AiProvider(Protocol):
    def generate(self, context: AiContextPayload) -> AiInsightResponse: ...
