"""Provider clients: WhatsApp (Meta Graph API) and email (Amazon SES v2).

Every failure is raised as one of three classes that carry a short code and nothing else: no
provider text, no chained cause (``raise ... from None``). The sender decides what to do:

- ``TemporaryProviderError``: the request provably never reached the provider; safe to retry.
- ``UnknownResultError``: the request may have been delivered; never retry blindly.
- ``PermanentProviderError``: the provider rejected it; do not retry.

Clients never run inside a database transaction and never log message text or addresses.
"""

import uuid
from functools import lru_cache
from typing import Any

import boto3
import requests
import urllib3
from botocore import exceptions as bexc
from botocore.config import Config
from django.conf import settings

GRAPH_URL = "https://graph.facebook.com/{version}/{phone_id}/messages"
TEMPLATE_TIMEOUT = (3, 7)
TEXT_TIMEOUT = (2, 3)
ERROR_CODE_MAX_LENGTH = 40  # Notification.error_code

CONNECT_FAILED = "CONNECT_FAILED"
UNKNOWN_RESULT = "UNKNOWN_RESULT"
CREDENTIALS = "CREDENTIALS"

SES_TEMPORARY_CODES = frozenset(
    {
        "TooManyRequestsException",
        "LimitExceededException",
        "SendingPausedException",
        "AccountSuspendedException",
    }
)


class ProviderError(Exception):
    def __init__(self, code: str) -> None:
        self.code = str(code)[:ERROR_CODE_MAX_LENGTH]
        super().__init__(self.code)


class TemporaryProviderError(ProviderError):
    """Never reached the provider, or the provider asked us to retry later."""


class UnknownResultError(ProviderError):
    """The request may or may not have been processed."""


class PermanentProviderError(ProviderError):
    """The provider rejected the request."""


# ---- WhatsApp ----


class WhatsAppClient:
    def send_template(self, *, to: str, template: str, parameters: list[str]) -> str:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": "ar"},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": p} for p in parameters],
                    }
                ],
            },
        }
        return self._post(payload, TEMPLATE_TIMEOUT)

    def send_text(self, *, to: str, body: str) -> str:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
        return self._post(payload, TEXT_TIMEOUT)

    def _post(self, payload: dict[str, Any], timeout: tuple[int, int]) -> str:
        url = GRAPH_URL.format(
            version=settings.WHATSAPP_API_VERSION, phone_id=settings.WHATSAPP_PHONE_NUMBER_ID
        )
        headers = {"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"}
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        except requests.exceptions.ConnectionError as exc:
            # ConnectTimeout and refused connections never reached Meta; everything else
            # (aborted, reset, remote closed) may have, so it is treated as unknown.
            reason = getattr(exc.args[0], "reason", None) if exc.args else None
            if isinstance(exc, requests.exceptions.ConnectTimeout) or isinstance(
                reason, urllib3.exceptions.NewConnectionError
            ):
                raise TemporaryProviderError(CONNECT_FAILED) from None
            raise UnknownResultError(UNKNOWN_RESULT) from None
        except requests.exceptions.Timeout:
            raise UnknownResultError(UNKNOWN_RESULT) from None
        except requests.exceptions.RequestException:
            raise UnknownResultError(UNKNOWN_RESULT) from None

        status = response.status_code
        body = _json_or_none(response)
        if 200 <= status < 300:
            message_id = _message_id(body)
            if message_id is None:
                raise UnknownResultError(UNKNOWN_RESULT) from None
            return message_id

        code = _meta_error_code(body) or f"HTTP_{status}"
        if status == 429 or status >= 500:
            raise TemporaryProviderError(code) from None
        raise PermanentProviderError(code) from None


def _json_or_none(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _message_id(body: Any) -> str | None:
    try:
        message_id = body["messages"][0]["id"]
    except (KeyError, IndexError, TypeError):
        return None
    return str(message_id) if message_id else None


def _meta_error_code(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if not isinstance(error, dict) or error.get("code") in (None, ""):
        return None
    return str(error["code"])


# ---- Email ----


@lru_cache(maxsize=1)
def _ses_client() -> Any:
    """The only place the SES client is built (credentials: default chain for now)."""
    return boto3.client(
        "sesv2",
        region_name=settings.SES_REGION,
        config=Config(
            connect_timeout=3,
            read_timeout=7,
            retries={"total_max_attempts": 1, "mode": "standard"},
        ),
    )


class EmailClient:
    def send(self, *, to: str, subject: str, html: str, text: str) -> str:
        try:
            response = _ses_client().send_email(
                FromEmailAddress=settings.SES_FROM_ADDRESS,
                Destination={"ToAddresses": [to]},
                Content={
                    "Simple": {
                        "Subject": {"Data": subject, "Charset": "UTF-8"},
                        "Body": {
                            "Html": {"Data": html, "Charset": "UTF-8"},
                            "Text": {"Data": text, "Charset": "UTF-8"},
                        },
                    }
                },
            )
        except (bexc.EndpointConnectionError, bexc.ConnectTimeoutError):
            raise TemporaryProviderError(CONNECT_FAILED) from None
        except (bexc.NoCredentialsError, bexc.CredentialRetrievalError):
            raise TemporaryProviderError(CREDENTIALS) from None
        except bexc.ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code") or "UNKNOWN_ERROR")
            http_status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
            if code in SES_TEMPORARY_CODES or http_status >= 500:
                raise TemporaryProviderError(code) from None
            raise PermanentProviderError(code) from None
        except bexc.BotoCoreError:
            # ReadTimeoutError, ConnectionClosedError and anything unclassified: the request
            # may have been sent, so never treat it as safe to retry.
            raise UnknownResultError(UNKNOWN_RESULT) from None

        message_id = response.get("MessageId")
        if not message_id:
            raise UnknownResultError(UNKNOWN_RESULT) from None
        return str(message_id)


# ---- Fakes ----


class _FakeBase:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.errors: list[Exception] = []

    def _record(self, entry: dict[str, Any]) -> str:
        if self.errors:
            raise self.errors.pop(0)
        self.sent.append(entry)
        return f"fake-{uuid.uuid4()}"


class FakeWhatsAppClient(_FakeBase):
    def send_template(self, *, to: str, template: str, parameters: list[str]) -> str:
        return self._record(
            {"kind": "template", "to": to, "template": template, "parameters": parameters}
        )

    def send_text(self, *, to: str, body: str) -> str:
        return self._record({"kind": "text", "to": to, "body": body})


class FakeEmailClient(_FakeBase):
    def send(self, *, to: str, subject: str, html: str, text: str) -> str:
        return self._record({"to": to, "subject": subject, "html": html, "text": text})


# ---- Selection ----


def _real() -> bool:
    return settings.NOTIFICATION_PROVIDERS == "real"


@lru_cache(maxsize=1)
def get_whatsapp_client() -> WhatsAppClient | FakeWhatsAppClient:
    return WhatsAppClient() if _real() else FakeWhatsAppClient()


@lru_cache(maxsize=1)
def get_email_client() -> EmailClient | FakeEmailClient:
    return EmailClient() if _real() else FakeEmailClient()
