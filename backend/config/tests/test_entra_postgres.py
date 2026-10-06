"""Entra-token PostgreSQL backend (PROMPT.md §26). The credential is mocked; nothing connects.
NOT VERIFIED against Azure Database for PostgreSQL — requires Azure credentials."""

import time
from unittest import mock

import pytest
from azure.core.credentials import AccessToken
from django.core.exceptions import ImproperlyConfigured
from django.db.utils import ConnectionHandler

from config.db.entra_postgres import base as entra

DB = {
    "ENGINE": "config.db.entra_postgres",
    "NAME": "medical",
    "USER": "id-medical-backend",
    "PASSWORD": "must-be-ignored",
    "HOST": "psql-medical.postgres.database.azure.com",
    "PORT": "5432",
    "OPTIONS": {"sslmode": "require"},
}


def wrapper(**overrides):
    return ConnectionHandler({"default": {**DB, **overrides}})["default"]


@pytest.fixture
def credential():
    entra.token_cache.clear()
    fake = mock.Mock()
    fake.get_token.return_value = AccessToken("token-1", int(time.time()) + 3600)
    with mock.patch("config.azure.get_azure_credential", return_value=fake):
        yield fake
    entra.token_cache.clear()


def test_engine_resolves_to_the_entra_wrapper():
    assert isinstance(wrapper(), entra.DatabaseWrapper)


def test_token_used_as_password(credential):
    params = wrapper().get_connection_params()
    assert params["password"] == "token-1"
    assert params["user"] == "id-medical-backend"
    assert params["sslmode"] == "require"
    credential.get_token.assert_called_once_with(entra.POSTGRES_SCOPE)


def test_token_reused_while_valid(credential):
    wrapper().get_connection_params()
    wrapper().get_connection_params()
    assert credential.get_token.call_count == 1


def test_token_refreshed_when_near_expiry(credential):
    credential.get_token.side_effect = [
        AccessToken("about-to-expire", int(time.time()) + 120),  # inside the 5-minute margin
        AccessToken("fresh", int(time.time()) + 3600),
    ]
    assert wrapper().get_connection_params()["password"] == "about-to-expire"
    assert wrapper().get_connection_params()["password"] == "fresh"
    assert credential.get_token.call_count == 2


@pytest.mark.parametrize("mode", ["disable", "allow", "prefer", ""])
def test_refuses_connections_without_tls(credential, mode):
    with pytest.raises(ImproperlyConfigured, match="sslmode"):
        wrapper(OPTIONS={"sslmode": mode} if mode else {}).get_connection_params()


def test_credential_failure_is_not_leaked_as_a_token(credential):
    from azure.core.exceptions import ClientAuthenticationError

    credential.get_token.side_effect = ClientAuthenticationError("no identity")
    with pytest.raises(ClientAuthenticationError):
        wrapper().get_connection_params()
    assert entra.token_cache.token is None
