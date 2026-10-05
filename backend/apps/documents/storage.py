"""Blob storage abstraction (PROMPT.md §19–20, decision D6).

`AzureBlobStorage` talks to Azure Blob Storage: a connection string locally (Azurite), or the
account URL + `DefaultAzureCredential` (managed identity) in Azure, where read URLs are
user-delegation SAS. The container is PRIVATE; SAS URLs are read-only, scoped to one blob and
expire within 5 minutes. `InMemoryStorage` backs unit tests only.
"""

import threading
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Protocol

from django.conf import settings
from django.utils.http import content_disposition_header

MAX_SAS_TTL_SECONDS = 300
SAS_CLOCK_SKEW = timedelta(minutes=1)


@dataclass(frozen=True)
class BlobInfo:
    name: str
    last_modified: datetime
    size: int


class BlobStorage(Protocol):
    def upload(self, blob_name: str, data: bytes, *, content_type: str) -> None: ...
    def download(self, blob_name: str) -> bytes: ...
    def delete(self, blob_name: str) -> None: ...  # idempotent
    def exists(self, blob_name: str) -> bool: ...
    def list(self, prefix: str) -> Iterator[BlobInfo]: ...
    def read_url(
        self, blob_name: str, *, ttl_seconds: int, content_type: str, filename: str
    ) -> str | None: ...


class InMemoryStorage:
    """Process-local store for unit tests. Never configured outside tests."""

    def __init__(self) -> None:
        self._blobs: dict[str, tuple[bytes, str, datetime]] = {}
        self._lock = threading.Lock()

    def upload(self, blob_name: str, data: bytes, *, content_type: str) -> None:
        with self._lock:
            if blob_name in self._blobs:
                raise FileExistsError(blob_name)
            self._blobs[blob_name] = (bytes(data), content_type, datetime.now(UTC))

    def download(self, blob_name: str) -> bytes:
        return self._blobs[blob_name][0]

    def delete(self, blob_name: str) -> None:
        with self._lock:
            self._blobs.pop(blob_name, None)

    def exists(self, blob_name: str) -> bool:
        return blob_name in self._blobs

    def list(self, prefix: str) -> Iterator[BlobInfo]:
        for name, (data, _, modified) in sorted(self._blobs.items()):
            if name.startswith(prefix):
                yield BlobInfo(name=name, last_modified=modified, size=len(data))

    def read_url(self, blob_name, *, ttl_seconds, content_type, filename) -> str | None:
        return None  # no SAS: the content view streams

    def clear(self) -> None:
        with self._lock:
            self._blobs.clear()

    def set_last_modified(self, blob_name: str, when: datetime) -> None:
        data, content_type, _ = self._blobs[blob_name]
        self._blobs[blob_name] = (data, content_type, when)


class AzureBlobStorage:
    def __init__(
        self,
        *,
        container: str,
        connection_string: str = "",
        account_url: str = "",
        create_container: bool = False,
    ) -> None:
        from azure.storage.blob import BlobServiceClient

        if connection_string:
            self._service = BlobServiceClient.from_connection_string(connection_string)
        elif account_url:
            from azure.identity import DefaultAzureCredential

            self._service = BlobServiceClient(account_url, credential=DefaultAzureCredential())
        else:
            raise ValueError("BLOB_CONNECTION_STRING or BLOB_ACCOUNT_URL must be set")
        self._container_name = container
        self._container = self._service.get_container_client(container)
        self._create_container = create_container

    def _blob(self, blob_name: str):
        return self._container.get_blob_client(blob_name)

    def upload(self, blob_name: str, data: bytes, *, content_type: str) -> None:
        from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
        from azure.storage.blob import ContentSettings

        content = ContentSettings(content_type=content_type)
        try:
            self._blob(blob_name).upload_blob(data, overwrite=False, content_settings=content)
        except ResourceNotFoundError:
            if not self._create_container:
                raise
            with suppress(ResourceExistsError):
                self._container.create_container()  # private: no public access level
            self._blob(blob_name).upload_blob(data, overwrite=False, content_settings=content)

    def download(self, blob_name: str) -> bytes:
        return self._blob(blob_name).download_blob().readall()

    def delete(self, blob_name: str) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        with suppress(ResourceNotFoundError):
            self._blob(blob_name).delete_blob(delete_snapshots="include")

    def exists(self, blob_name: str) -> bool:
        return self._blob(blob_name).exists()

    def list(self, prefix: str) -> Iterator[BlobInfo]:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            for blob in self._container.list_blobs(name_starts_with=prefix):
                yield BlobInfo(name=blob.name, last_modified=blob.last_modified, size=blob.size)
        except ResourceNotFoundError:  # container not created yet: nothing stored
            return

    def read_url(self, blob_name, *, ttl_seconds, content_type, filename) -> str | None:
        """Read-only SAS for ONE blob, valid at most 5 minutes from now."""
        from azure.storage.blob import BlobSasPermissions, generate_blob_sas

        now = datetime.now(UTC)
        expiry = now + timedelta(seconds=min(ttl_seconds, MAX_SAS_TTL_SECONDS))
        start = now - SAS_CLOCK_SKEW
        signing = {}
        credential = self._service.credential
        account_key = getattr(credential, "account_key", None)
        if account_key:
            signing["account_key"] = account_key
        else:
            signing["user_delegation_key"] = self._service.get_user_delegation_key(start, expiry)
        token = generate_blob_sas(
            account_name=self._service.account_name,
            container_name=self._container_name,
            blob_name=blob_name,
            permission=BlobSasPermissions(read=True),
            expiry=expiry,
            start=start,
            content_type=content_type,
            content_disposition=content_disposition_header(False, filename),
            **signing,
        )
        return f"{self._blob(blob_name).url}?{token}"


_memory_storage = InMemoryStorage()


@lru_cache(maxsize=4)
def _azure_storage(
    container: str, connection_string: str, account_url: str, create_container: bool
) -> AzureBlobStorage:
    # One client (and one managed-identity credential with its token cache) per configuration.
    return AzureBlobStorage(
        container=container,
        connection_string=connection_string,
        account_url=account_url,
        create_container=create_container,
    )


def get_storage() -> BlobStorage:
    if settings.BLOB_BACKEND == "memory":
        return _memory_storage
    return _azure_storage(
        settings.BLOB_CONTAINER,
        settings.BLOB_CONNECTION_STRING,
        settings.BLOB_ACCOUNT_URL,
        settings.BLOB_CREATE_CONTAINER,
    )
