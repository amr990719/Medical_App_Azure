"""Azure OpenAI vision provider (PROMPT.md §21.2) — implemented in Session 7.

Will call a vision-capable chat deployment with structured outputs
(`apps.ocr.schemas.SCHEMAS[...].json_schema()`), authenticated with the Container App's managed
identity (`Cognitive Services OpenAI User`). Until then it refuses, so OCR_PROVIDER=azure_openai
yields OCR_UNAVAILABLE instead of sending anything anywhere.
"""

from typing import Any

from django.conf import settings

from apps.reference.constants import DocumentType

from .base import OcrProviderError


class AzureOpenAIProvider:
    name = "azure_openai"

    def __init__(self) -> None:
        self.endpoint = settings.AZURE_OPENAI_ENDPOINT
        self.deployment = settings.AZURE_OPENAI_DEPLOYMENT
        self.api_version = settings.AZURE_OPENAI_API_VERSION

    def extract(
        self, *, image: bytes, content_type: str, document_type: DocumentType
    ) -> dict[str, Any]:
        raise OcrProviderError("Azure OpenAI provider is not implemented yet (Session 7)")
