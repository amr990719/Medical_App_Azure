"""Managed-identity Blob access and user-delegation SAS (PROMPT.md §19–20, plan Task 7.1).

The SDK is used for real (client construction, SAS signing) but the credential and the
user-delegation-key request are mocked: NOT VERIFIED against a real storage account — requires
Azure credentials (and the `Storage Blob Data Contributor` + `Storage Blob Delegator` roles).
"""

import base64
from datetime import UTC, datetime, timedelta
from unittest import mock
from urllib.parse import parse_qs, urlparse

import pytest
from azure.storage.blob import UserDelegationKey

from apps.documents import storage as storage_module
from apps.documents.azurite import azurite_connection_string
from apps.documents.storage import AzureBlobStorage

ACCOUNT_URL = "https://stmedicaltest.blob.core.windows.net"


def fake_delegation_key(start: datetime, expiry: datetime) -> UserDelegationKey:
    key = UserDelegationKey()
    key.signed_oid = "11111111-1111-1111-1111-111111111111"
    key.signed_tid = "22222222-2222-2222-2222-222222222222"
    key.signed_start = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    key.signed_expiry = expiry.strftime("%Y-%m-%dT%H:%M:%SZ")
    key.signed_service = "b"
    key.signed_version = "2025-01-05"
    key.value = base64.b64encode(b"k" * 32).decode()
    return key


@pytest.fixture
def credential():
    fake = mock.Mock(spec=["get_token", "get_token_info"], name="DefaultAzureCredential")
    with mock.patch("config.azure.get_azure_credential", return_value=fake):
        yield fake


@pytest.fixture
def identity_storage(credential):
    storage = AzureBlobStorage(account_url=ACCOUNT_URL, container="medical-documents")
    calls = []

    def get_key(start, expiry, **kwargs):
        calls.append((start, expiry))
        return fake_delegation_key(start, expiry)

    storage._service.get_user_delegation_key = get_key
    return storage, calls


def sas(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def test_uses_default_credential_otherwise(credential):
    with mock.patch("azure.storage.blob.BlobServiceClient") as service_cls:
        AzureBlobStorage(account_url=ACCOUNT_URL, container="medical-documents")
    service_cls.assert_called_once_with(ACCOUNT_URL, credential=credential)
    service_cls.from_connection_string.assert_not_called()


def test_uses_connection_string_when_present(credential):
    connection = azurite_connection_string(port=1)
    with mock.patch("azure.storage.blob.BlobServiceClient") as service_cls:
        AzureBlobStorage(
            connection_string=connection, account_url=ACCOUNT_URL, container="medical-documents"
        )
    service_cls.from_connection_string.assert_called_once_with(connection)
    service_cls.assert_not_called()  # no managed-identity client when a connection string is set


def test_requires_an_endpoint():
    with pytest.raises(ValueError, match="BLOB_ACCOUNT_URL"):
        AzureBlobStorage(container="medical-documents")


def test_sas_expiry_le_300s_signed_with_a_user_delegation_key(identity_storage):
    storage, _ = identity_storage
    url = storage.read_url(
        "applications/a/doctor/x.png", ttl_seconds=3600, content_type="image/png", filename="x.png"
    )
    params = sas(url)
    assert url.startswith(f"{ACCOUNT_URL}/medical-documents/applications/a/doctor/x.png?")
    assert params["skoid"] == "11111111-1111-1111-1111-111111111111"  # user delegation, no key
    assert params["sp"] == "r"
    assert params["sr"] == "b"
    expiry = datetime.strptime(params["se"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    assert 0 < (expiry - datetime.now(UTC)).total_seconds() <= 300
    assert params["rsct"] == "image/png"


def test_user_delegation_key_cached_for_an_hour(identity_storage):
    storage, calls = identity_storage
    for _ in range(3):
        storage.read_url("x.png", ttl_seconds=300, content_type="image/png", filename="x.png")
    assert len(calls) == 1
    start, expiry = calls[0]
    assert timedelta(minutes=59) <= expiry - datetime.now(UTC) <= timedelta(hours=1)
    assert start <= datetime.now(UTC)


def test_user_delegation_key_renewed_before_it_can_outlive_the_sas(identity_storage):
    storage, calls = identity_storage
    storage.read_url("x.png", ttl_seconds=300, content_type="image/png", filename="x.png")
    later = datetime.now(UTC) + timedelta(minutes=57)  # a 5-minute SAS would outlive the key
    with mock.patch.object(storage_module, "_utcnow", return_value=later):
        storage.read_url("x.png", ttl_seconds=300, content_type="image/png", filename="x.png")
    assert len(calls) == 2


def test_get_storage_passes_the_account_url(settings, credential):
    settings.BLOB_BACKEND = "azure"
    settings.BLOB_CONNECTION_STRING = ""
    settings.BLOB_ACCOUNT_URL = ACCOUNT_URL
    storage_module._azure_storage.cache_clear()
    try:
        with mock.patch("azure.storage.blob.BlobServiceClient") as service_cls:
            storage_module.get_storage()
        service_cls.assert_called_once_with(ACCOUNT_URL, credential=credential)
    finally:
        storage_module._azure_storage.cache_clear()
