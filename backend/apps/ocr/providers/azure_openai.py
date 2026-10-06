"""Azure OpenAI vision provider (PROMPT.md §21.2–21.3).

Sends ONE image to a vision-capable chat deployment with the Arabic extraction instructions of
`apps.ocr.schemas` and a strict JSON schema (structured outputs), authenticated with the
Container App's managed identity (`Cognitive Services OpenAI User` role; no API key anywhere).
The raw fields are returned un-normalized; `apps.ocr.services` normalizes them.

Privacy: nothing about the image, the prompt or the answer is logged; every failure becomes an
`OcrProviderError` with a fixed message and no chained SDK exception (SDK errors can echo the
request or response). `store=False` asks the service not to keep the completion. Abuse
monitoring / data residency are documented in docs/ocr.md and docs/security.md.
NOT VERIFIED against a real deployment — requires Azure credentials.
"""

import base64
import json
from functools import lru_cache
from typing import Any

from django.conf import settings

from apps.ocr.schemas import SCHEMAS
from apps.reference.constants import DocumentType

from .base import OcrProviderError

COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"
REQUEST_TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 1
MAX_COMPLETION_TOKENS = 1000

SYSTEM_INSTRUCTIONS = (
    "أنت مساعد لاستخراج البيانات من صور المستندات الرسمية المصرية.\n"
    "أرجع البيانات المطلوبة فقط بصيغة JSON المحددة، ولا تخمّن: "
    "إذا كانت القيمة غير واضحة أو غير موجودة فاتركها فارغة.\n\n"
)
USER_INSTRUCTION = "استخرج البيانات المطلوبة من هذه الصورة."


@lru_cache(maxsize=2)
def _client(endpoint: str, api_version: str):
    """One client per configuration: keeps the HTTP connection pool and the token provider."""
    import openai
    from azure.identity import get_bearer_token_provider

    from config.azure import get_azure_credential

    return openai.AzureOpenAI(
        azure_endpoint=endpoint,
        api_version=api_version,
        azure_ad_token_provider=get_bearer_token_provider(
            get_azure_credential(), COGNITIVE_SERVICES_SCOPE
        ),
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=MAX_RETRIES,
    )


class AzureOpenAIProvider:
    name = "azure_openai"

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        deployment: str | None = None,
        api_version: str | None = None,
        client=None,
    ) -> None:
        self.endpoint = settings.AZURE_OPENAI_ENDPOINT if endpoint is None else endpoint
        self.deployment = settings.AZURE_OPENAI_DEPLOYMENT if deployment is None else deployment
        self.api_version = settings.AZURE_OPENAI_API_VERSION if api_version is None else api_version
        self._injected_client = client

    def _get_client(self):
        if not (self.endpoint and self.deployment and self.api_version):
            raise OcrProviderError("Azure OpenAI provider is not configured")
        return self._injected_client or _client(self.endpoint, self.api_version)

    def extract(
        self, *, image: bytes, content_type: str, document_type: DocumentType
    ) -> dict[str, Any]:
        schema = SCHEMAS.get(DocumentType(document_type))
        if schema is None:
            raise OcrProviderError("document type has no extraction schema")
        client = self._get_client()
        data_url = f"data:{content_type};base64,{base64.b64encode(image).decode('ascii')}"
        try:
            response = client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": SYSTEM_INSTRUCTIONS + schema.prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": USER_INSTRUCTION},
                            {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                        ],
                    },
                ],
                response_format={"type": "json_schema", "json_schema": schema.json_schema()},
                max_completion_tokens=MAX_COMPLETION_TOKENS,
                store=False,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # openai / httpx / azure-identity errors; none may leak
            raise OcrProviderError(f"Azure OpenAI request failed ({type(exc).__name__})") from None

        return _parse(response, schema.properties)


def _parse(response, properties: tuple[str, ...]) -> dict[str, Any]:
    try:
        choice = response.choices[0]
        message = choice.message
    except (AttributeError, IndexError):
        raise OcrProviderError("Azure OpenAI returned no choice") from None
    if getattr(message, "refusal", None):
        raise OcrProviderError("Azure OpenAI refused the request")
    if choice.finish_reason != "stop" or not message.content:
        raise OcrProviderError(f"Azure OpenAI did not finish ({choice.finish_reason})")
    try:
        raw = json.loads(message.content)
    except ValueError:
        raise OcrProviderError("Azure OpenAI returned invalid JSON") from None
    if not isinstance(raw, dict):
        raise OcrProviderError("Azure OpenAI returned a non-object")
    return {key: raw[key] for key in properties if isinstance(raw.get(key), str)}
