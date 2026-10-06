"""One shared Azure credential (managed identity in Azure). NOT VERIFIED against real Azure:
the credential is constructed but never asked for a token here."""

from unittest import mock

import pytest

from config import azure


@pytest.fixture(autouse=True)
def _fresh_credential():
    azure.get_azure_credential.cache_clear()
    yield
    azure.get_azure_credential.cache_clear()


def test_credential_is_shared(monkeypatch):
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    with mock.patch("azure.identity.DefaultAzureCredential") as dac:
        first = azure.get_azure_credential()
        second = azure.get_azure_credential()
    assert first is second
    dac.assert_called_once_with(managed_identity_client_id=None)


def test_user_assigned_identity_from_azure_client_id(monkeypatch):
    monkeypatch.setenv("AZURE_CLIENT_ID", "00000000-0000-0000-0000-00000000c1d0")
    with mock.patch("azure.identity.DefaultAzureCredential") as dac:
        azure.get_azure_credential()
    dac.assert_called_once_with(managed_identity_client_id="00000000-0000-0000-0000-00000000c1d0")
