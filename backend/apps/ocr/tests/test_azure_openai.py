"""Azure OpenAI OCR provider (PROMPT.md §21.2–21.3, plan Task 7.4).

The real `openai.AzureOpenAI` client runs against an in-process mock transport, so the request
that would go over the wire is asserted exactly; the managed-identity token provider is a stub.
NOT VERIFIED against a real Azure OpenAI deployment — requires Azure credentials.
"""

import base64
import json
import logging
from unittest import mock

import httpx2
import openai
import pytest

from apps.ocr.providers import azure_openai as provider_module
from apps.ocr.providers import get_provider
from apps.ocr.providers.azure_openai import COGNITIVE_SERVICES_SCOPE, AzureOpenAIProvider
from apps.ocr.providers.base import OcrProviderError
from apps.ocr.schemas import NATIONAL_ID_FRONT, SYNDICATE_ID
from apps.reference.constants import DocumentType as T

ENDPOINT = "https://aoai-medical-test.openai.azure.com/"
DEPLOYMENT = "gpt-vision-test"
API_VERSION = "2024-10-21"
IMAGE = b"\x89PNG\r\n\x1a\n" + b"pixels" * 10
NATIONAL_ID = "28506150101234"
FRONT = {
    "member_name": "أحمد محمد علي حسن",
    "national_id": NATIONAL_ID,
    "governorate": "القاهرة",
    "address": "١٢ شارع عباس العقاد",
    "neighborhood": "مدينة نصر",
}


def completion(content: str | None, *, finish_reason="stop", refusal=None) -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": DEPLOYMENT,
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": {"role": "assistant", "content": content, "refusal": refusal},
            }
        ],
    }


class Wire:
    """Captures requests and answers with a canned response (or raises a transport error)."""

    def __init__(self, response: dict | None = None, *, status=200, error: Exception | None = None):
        self.requests: list[httpx2.Request] = []
        self.response = response if response is not None else completion(json.dumps(FRONT))
        self.status = status
        self.error = error

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self.error:
            raise self.error
        return httpx2.Response(self.status, json=self.response)

    @property
    def body(self) -> dict:
        return json.loads(self.requests[-1].content)


def make_provider(wire: Wire) -> AzureOpenAIProvider:
    client = openai.AzureOpenAI(
        azure_endpoint=ENDPOINT,
        api_version=API_VERSION,
        azure_ad_token_provider=lambda: "entra-token",
        http_client=httpx2.Client(transport=httpx2.MockTransport(wire)),
        max_retries=0,
    )
    return AzureOpenAIProvider(
        endpoint=ENDPOINT, deployment=DEPLOYMENT, api_version=API_VERSION, client=client
    )


def test_builds_json_schema_request():
    wire = Wire()
    raw = make_provider(wire).extract(
        image=IMAGE, content_type="image/png", document_type=T.NATIONAL_ID_FRONT
    )
    assert raw == FRONT

    request = wire.requests[0]
    assert request.url.path == f"/openai/deployments/{DEPLOYMENT}/chat/completions"
    assert request.url.params["api-version"] == API_VERSION
    assert request.headers["authorization"] == "Bearer entra-token"  # managed identity, no key
    assert "api-key" not in request.headers

    body = wire.body
    assert body["model"] == DEPLOYMENT
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": NATIONAL_ID_FRONT.json_schema(),
    }
    system, user = body["messages"]
    assert system["role"] == "system"
    assert NATIONAL_ID_FRONT.prompt in system["content"]
    assert user["role"] == "user"
    image_part = next(p for p in user["content"] if p["type"] == "image_url")
    expected = "data:image/png;base64," + base64.b64encode(IMAGE).decode()
    assert image_part["image_url"]["url"] == expected


def test_prompt_and_schema_follow_the_document_type():
    wire = Wire(completion(json.dumps(dict.fromkeys(SYNDICATE_ID.properties, ""))))
    make_provider(wire).extract(image=IMAGE, content_type="image/png", document_type=T.SYNDICATE_ID)
    assert wire.body["response_format"]["json_schema"]["name"] == "syndicate_id"
    assert SYNDICATE_ID.prompt in wire.body["messages"][0]["content"]


def test_request_has_a_timeout_and_no_storage():
    wire = Wire()
    make_provider(wire).extract(
        image=IMAGE, content_type="image/png", document_type=T.NATIONAL_ID_FRONT
    )
    assert wire.body.get("store") is False
    assert wire.requests[0].extensions["timeout"]["read"] == provider_module.REQUEST_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    "wire",
    [
        Wire(error=httpx2.ConnectError("connection refused")),
        Wire({"error": {"code": "429", "message": "Rate limit"}}, status=429),
        Wire({"error": {"code": "content_filter", "message": "filtered"}}, status=400),
        Wire({"error": {"code": "PermissionDenied", "message": "no role"}}, status=401),
        Wire(completion("not json")),
        Wire(completion(None, refusal="I can't help with that.")),
        Wire(completion('{"member_name": "x"', finish_reason="length")),
        Wire(completion(json.dumps(["not", "an", "object"]))),
    ],
    ids=["network", "throttled", "content-filter", "auth", "bad-json", "refusal", "truncated",
         "not-object"],
)  # fmt: skip
def test_sdk_error_maps_to_ocr_provider_error(wire):
    with pytest.raises(OcrProviderError) as exc:
        make_provider(wire).extract(
            image=IMAGE, content_type="image/png", document_type=T.NATIONAL_ID_FRONT
        )
    assert NATIONAL_ID not in str(exc.value)
    assert exc.value.__cause__ is None  # SDK exceptions (which may echo the payload) dropped


def test_credential_failure_maps_to_ocr_provider_error():
    from azure.core.exceptions import ClientAuthenticationError

    def no_identity():
        raise ClientAuthenticationError("ManagedIdentityCredential authentication unavailable")

    wire = Wire()
    client = openai.AzureOpenAI(
        azure_endpoint=ENDPOINT,
        api_version=API_VERSION,
        azure_ad_token_provider=no_identity,
        http_client=httpx2.Client(transport=httpx2.MockTransport(wire)),
        max_retries=0,
    )
    provider = AzureOpenAIProvider(
        endpoint=ENDPOINT, deployment=DEPLOYMENT, api_version=API_VERSION, client=client
    )
    with pytest.raises(OcrProviderError):
        provider.extract(image=IMAGE, content_type="image/png", document_type=T.NATIONAL_ID_FRONT)
    assert wire.requests == []


def test_unsupported_document_type_is_refused_without_a_call():
    wire = Wire()
    with pytest.raises(OcrProviderError):
        make_provider(wire).extract(
            image=IMAGE, content_type="image/png", document_type=T.PAYMENT_RECEIPT
        )
    assert wire.requests == []


def test_no_logging_of_payload(caplog):
    wire = Wire()
    caplog.set_level(logging.DEBUG)  # every logger, including openai / httpx2 / azure
    make_provider(wire).extract(
        image=IMAGE, content_type="image/png", document_type=T.NATIONAL_ID_FRONT
    )
    with pytest.raises(OcrProviderError):
        make_provider(Wire(completion("not json " + NATIONAL_ID))).extract(
            image=IMAGE, content_type="image/png", document_type=T.NATIONAL_ID_FRONT
        )
    text = caplog.text
    assert NATIONAL_ID not in text
    assert "أحمد" not in text
    assert base64.b64encode(IMAGE).decode() not in text
    assert "شارع" not in text


def test_default_client_uses_managed_identity_bearer_tokens(settings):
    provider_module._client.cache_clear()
    credential = object()
    token_provider = object()
    try:
        with (
            mock.patch("config.azure.get_azure_credential", return_value=credential),
            mock.patch(
                "azure.identity.get_bearer_token_provider", return_value=token_provider
            ) as bearer,
            mock.patch("openai.AzureOpenAI") as client_cls,
        ):
            provider_module._client(ENDPOINT, API_VERSION)
        bearer.assert_called_once_with(credential, COGNITIVE_SERVICES_SCOPE)
        kwargs = client_cls.call_args.kwargs
        assert kwargs["azure_endpoint"] == ENDPOINT
        assert kwargs["api_version"] == API_VERSION
        assert kwargs["azure_ad_token_provider"] is token_provider
        assert kwargs["timeout"] == provider_module.REQUEST_TIMEOUT_SECONDS
        assert "api_key" not in kwargs
    finally:
        provider_module._client.cache_clear()


def test_get_provider_selects_azure_openai_from_settings(settings):
    settings.OCR_PROVIDER = "azure_openai"
    settings.AZURE_OPENAI_ENDPOINT = ENDPOINT
    settings.AZURE_OPENAI_DEPLOYMENT = DEPLOYMENT
    settings.AZURE_OPENAI_API_VERSION = API_VERSION
    provider = get_provider()
    assert isinstance(provider, AzureOpenAIProvider)
    assert provider.deployment == DEPLOYMENT


@pytest.mark.parametrize(
    "missing", ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_API_VERSION"]
)
def test_unconfigured_provider_refuses(settings, missing):
    settings.AZURE_OPENAI_ENDPOINT = ENDPOINT
    settings.AZURE_OPENAI_DEPLOYMENT = DEPLOYMENT
    settings.AZURE_OPENAI_API_VERSION = API_VERSION
    setattr(settings, missing, "")
    with pytest.raises(OcrProviderError, match="not configured"):
        AzureOpenAIProvider().extract(
            image=IMAGE, content_type="image/png", document_type=T.NATIONAL_ID_FRONT
        )
