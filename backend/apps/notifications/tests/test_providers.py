from unittest import mock

import boto3
import pytest
import requests
import urllib3
from botocore import exceptions as bexc
from botocore.stub import Stubber

from apps.notifications import providers
from apps.notifications.providers import (
    EmailClient,
    FakeEmailClient,
    FakeWhatsAppClient,
    PermanentProviderError,
    ProviderError,
    TemporaryProviderError,
    UnknownResultError,
    WhatsAppClient,
)


@pytest.fixture
def wa_settings(settings):
    settings.WHATSAPP_PHONE_NUMBER_ID = "111"
    settings.WHATSAPP_API_VERSION = "v99.0"
    settings.WHATSAPP_ACCESS_TOKEN = "tok-123"
    return settings


def _response(status=200, body=None):
    resp = mock.Mock()
    resp.status_code = status
    if body is None:
        resp.json.side_effect = ValueError("no json")
    else:
        resp.json.return_value = body
    return resp


def _post(response=None, side_effect=None):
    return mock.patch(
        "apps.notifications.providers.requests.post", return_value=response, side_effect=side_effect
    )


def _send():
    return WhatsAppClient().send_template(to="201000000000", template="t", parameters=["a"])


# ---- ProviderError ----


def test_provider_error_code_is_truncated_to_column_size():
    exc = ProviderError("X" * 100)
    assert exc.code == "X" * 40
    assert str(exc) == "X" * 40


def test_provider_error_code_is_a_string():
    assert ProviderError(131026).code == "131026"


# ---- WhatsApp ----


def test_whatsapp_template_payload(wa_settings):
    with _post(_response(200, {"messages": [{"id": "wamid.1"}]})) as post:
        result = WhatsAppClient().send_template(
            to="201000000000", template="app_approved", parameters=["MED-1", "x"]
        )
    assert result == "wamid.1"
    args, kwargs = post.call_args
    assert args[0] == "https://graph.facebook.com/v99.0/111/messages"
    assert kwargs["json"] == {
        "messaging_product": "whatsapp",
        "to": "201000000000",
        "type": "template",
        "template": {
            "name": "app_approved",
            "language": {"code": "ar"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": "MED-1"},
                        {"type": "text", "text": "x"},
                    ],
                }
            ],
        },
    }
    assert kwargs["timeout"] == (3, 7)
    assert kwargs["headers"]["Authorization"] == "Bearer tok-123"


def test_send_text_uses_short_timeout(wa_settings):
    with _post(_response(200, {"messages": [{"id": "wamid.2"}]})) as post:
        result = WhatsAppClient().send_text(to="201000000000", body="hi")
    assert result == "wamid.2"
    kwargs = post.call_args.kwargs
    assert kwargs["timeout"] == (2, 3)
    assert kwargs["json"]["type"] == "text"
    assert kwargs["json"]["text"] == {"body": "hi"}


def test_whatsapp_400_is_permanent_with_metas_code(wa_settings):
    body = {"error": {"code": 131026, "message": "Message undeliverable for 2010000"}}
    with _post(_response(400, body)), pytest.raises(PermanentProviderError) as ei:
        _send()
    assert ei.value.code == "131026"
    assert "undeliverable" not in str(ei.value)


def test_whatsapp_401_without_code_uses_http_status(wa_settings):
    with _post(_response(401, None)), pytest.raises(PermanentProviderError) as ei:
        _send()
    assert ei.value.code == "HTTP_401"


@pytest.mark.parametrize("status", [429, 500, 503])
def test_whatsapp_retryable_status_is_temporary(wa_settings, status):
    with _post(_response(status, None)), pytest.raises(TemporaryProviderError) as ei:
        _send()
    assert ei.value.code == f"HTTP_{status}"


def test_whatsapp_connection_refused_is_temporary(wa_settings):
    reason = urllib3.exceptions.NewConnectionError(None, "refused")
    exc = requests.exceptions.ConnectionError(urllib3.exceptions.MaxRetryError(None, "u", reason))
    with _post(side_effect=exc), pytest.raises(TemporaryProviderError) as ei:
        _send()
    assert ei.value.code == "CONNECT_FAILED"


def test_whatsapp_connect_timeout_is_temporary(wa_settings):
    with (
        _post(side_effect=requests.exceptions.ConnectTimeout("slow")),
        pytest.raises(TemporaryProviderError) as ei,
    ):
        _send()
    assert ei.value.code == "CONNECT_FAILED"


def test_whatsapp_read_timeout_is_unknown(wa_settings):
    with (
        _post(side_effect=requests.exceptions.ReadTimeout("slow")),
        pytest.raises(UnknownResultError) as ei,
    ):
        _send()
    assert ei.value.code == "UNKNOWN_RESULT"


def test_whatsapp_connection_dropped_after_send_is_unknown(wa_settings):
    exc = requests.exceptions.ConnectionError(urllib3.exceptions.ProtocolError("aborted"))
    with _post(side_effect=exc), pytest.raises(UnknownResultError) as ei:
        _send()
    assert ei.value.code == "UNKNOWN_RESULT"


def test_whatsapp_200_without_an_id_is_unknown(wa_settings):
    with _post(_response(200, {"messages": []})), pytest.raises(UnknownResultError) as ei:
        _send()
    assert ei.value.code == "UNKNOWN_RESULT"


def test_whatsapp_200_with_non_json_body_is_unknown(wa_settings):
    with _post(_response(200, None)), pytest.raises(UnknownResultError):
        _send()


def test_errors_carry_no_provider_text_or_chained_cause(wa_settings):
    with (
        _post(side_effect=requests.exceptions.ReadTimeout("secret 201000000000")),
        pytest.raises(UnknownResultError) as ei,
    ):
        _send()
    exc = ei.value
    assert exc.__cause__ is None
    assert exc.__suppress_context__ is True
    assert str(exc) == exc.code


def test_http_errors_also_suppress_context(wa_settings):
    with (
        _post(_response(400, {"error": {"code": 1, "message": "leaky text"}})),
        pytest.raises(PermanentProviderError) as ei,
    ):
        _send()
    assert ei.value.__cause__ is None
    assert ei.value.__suppress_context__ is True
    assert str(ei.value) == "1"


# ---- SES ----


@pytest.fixture
def ses(settings):
    settings.SES_REGION = "eu-central-1"
    settings.SES_FROM_ADDRESS = "from@example.test"
    client = boto3.client(
        "sesv2",
        region_name="eu-central-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    with mock.patch("apps.notifications.providers._ses_client", return_value=client):
        yield client


def test_ses_client_config(settings, monkeypatch):
    # Never read the developer's real AWS profile or credentials.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_CONFIG_FILE", "NUL")
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", "NUL")
    settings.SES_REGION = "eu-central-1"
    client = providers._ses_client()
    cfg = client.meta.config
    assert cfg.connect_timeout == 3
    assert cfg.read_timeout == 7
    assert cfg.retries["total_max_attempts"] == 1
    assert client.meta.region_name == "eu-central-1"
    assert providers._ses_client() is client


def _send_email():
    return EmailClient().send(to="dr@example.test", subject="موضوع", html="<p>نص</p>", text="نص")


def test_ses_payload_is_utf8_html_and_text(ses):
    with Stubber(ses) as stub:
        stub.add_response(
            "send_email",
            {"MessageId": "ses-1"},
            {
                "FromEmailAddress": "from@example.test",
                "Destination": {"ToAddresses": ["dr@example.test"]},
                "Content": {
                    "Simple": {
                        "Subject": {"Data": "موضوع", "Charset": "UTF-8"},
                        "Body": {
                            "Html": {"Data": "<p>نص</p>", "Charset": "UTF-8"},
                            "Text": {"Data": "نص", "Charset": "UTF-8"},
                        },
                    }
                },
            },
        )
        assert _send_email() == "ses-1"


def test_ses_message_rejected_is_permanent(ses):
    with Stubber(ses) as stub:
        stub.add_client_error("send_email", "MessageRejected", http_status_code=400)
        with pytest.raises(PermanentProviderError) as ei:
            _send_email()
    assert ei.value.code == "MessageRejected"
    assert ei.value.__cause__ is None


@pytest.mark.parametrize(
    "code",
    [
        "TooManyRequestsException",
        "LimitExceededException",
        "SendingPausedException",
        "AccountSuspendedException",
    ],
)
def test_ses_account_level_errors_are_temporary(ses, code):
    with Stubber(ses) as stub:
        stub.add_client_error("send_email", code, http_status_code=400)
        with pytest.raises(TemporaryProviderError) as ei:
            _send_email()
    assert ei.value.code == code


def test_ses_5xx_is_temporary(ses):
    with Stubber(ses) as stub:
        stub.add_client_error("send_email", "InternalFailure", http_status_code=500)
        with pytest.raises(TemporaryProviderError) as ei:
            _send_email()
    assert ei.value.code == "InternalFailure"


def _raising(ses, exc):
    return mock.patch.object(ses, "send_email", side_effect=exc)


@pytest.mark.parametrize(
    "exc",
    [
        bexc.EndpointConnectionError(endpoint_url="https://x"),
        bexc.ConnectTimeoutError(endpoint_url="https://x"),
    ],
)
def test_ses_connect_error_is_temporary(ses, exc):
    with _raising(ses, exc), pytest.raises(TemporaryProviderError) as ei:
        _send_email()
    assert ei.value.code == "CONNECT_FAILED"


@pytest.mark.parametrize(
    "exc",
    [
        bexc.ReadTimeoutError(endpoint_url="https://x"),
        bexc.ConnectionClosedError(endpoint_url="https://x"),
    ],
)
def test_ses_read_timeout_is_unknown(ses, exc):
    with _raising(ses, exc), pytest.raises(UnknownResultError) as ei:
        _send_email()
    assert ei.value.code == "UNKNOWN_RESULT"
    assert ei.value.__cause__ is None


@pytest.mark.parametrize(
    "exc",
    [
        bexc.NoCredentialsError(),
        bexc.CredentialRetrievalError(provider="p", error_msg="m"),
    ],
)
def test_missing_credentials_are_temporary(ses, exc):
    with _raising(ses, exc), pytest.raises(TemporaryProviderError) as ei:
        _send_email()
    assert ei.value.code == "CREDENTIALS"


# ---- Fakes and selection ----


def test_settings_select_fakes_in_tests():
    assert isinstance(providers.get_whatsapp_client(), FakeWhatsAppClient)
    assert isinstance(providers.get_email_client(), FakeEmailClient)
    assert providers.get_whatsapp_client() is providers.get_whatsapp_client()


def test_settings_select_real_clients_when_live(settings):
    settings.NOTIFICATION_PROVIDERS = "live"
    assert isinstance(providers.get_whatsapp_client(), WhatsAppClient)
    assert isinstance(providers.get_email_client(), EmailClient)


def test_fake_whatsapp_records_and_returns_ids():
    fake = FakeWhatsAppClient()
    a = fake.send_template(to="1", template="t", parameters=["p"])
    b = fake.send_text(to="1", body="hi")
    assert a.startswith("fake-") and b.startswith("fake-") and a != b
    assert fake.sent == [
        {"kind": "template", "to": "1", "template": "t", "parameters": ["p"]},
        {"kind": "text", "to": "1", "body": "hi"},
    ]


def test_fake_errors_are_raised_once_in_order_and_not_recorded():
    fake = FakeEmailClient()
    fake.errors.append(TemporaryProviderError("X"))
    with pytest.raises(TemporaryProviderError):
        fake.send(to="a", subject="s", html="h", text="t")
    assert fake.sent == []
    assert fake.send(to="a", subject="s", html="h", text="t").startswith("fake-")
    assert len(fake.sent) == 1
