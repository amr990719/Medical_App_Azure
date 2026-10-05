import os
import socket
import uuid
from contextlib import suppress
from pathlib import Path

import environ
import pytest
from django.core.cache import cache

# Local overrides shared with docker compose (e.g. AZURITE_BLOB_PORT) live in the root `.env`.
environ.Env.read_env(Path(__file__).resolve().parent.parent / ".env")


def local_azurite_connection_string() -> str:
    from apps.documents.azurite import azurite_connection_string

    return azurite_connection_string(int(os.environ.get("AZURITE_BLOB_PORT", "10000")))


def azurite_reachable() -> bool:
    port = int(os.environ.get("AZURITE_BLOB_PORT", "10000"))
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture(autouse=True)
def _clean_shared_state():
    """Throttle counters (cache) and the in-memory blob store start empty for every test."""
    from apps.documents.storage import _memory_storage

    cache.clear()
    _memory_storage.clear()
    yield
    cache.clear()
    _memory_storage.clear()


@pytest.fixture
def azurite_settings(settings):
    """Point the storage at the docker compose Azurite (a throwaway container per test)."""
    if not azurite_reachable():
        pytest.skip("Azurite is not running (docker compose up -d azurite)")
    settings.BLOB_BACKEND = "azure"
    settings.BLOB_CONNECTION_STRING = local_azurite_connection_string()
    settings.BLOB_CONTAINER = f"test-{uuid.uuid4().hex[:12]}"
    settings.BLOB_CREATE_CONTAINER = True
    yield settings
    from azure.storage.blob import BlobServiceClient

    service = BlobServiceClient.from_connection_string(settings.BLOB_CONNECTION_STRING)
    with suppress(Exception):  # best-effort cleanup of the throwaway container
        service.delete_container(settings.BLOB_CONTAINER)


@pytest.fixture
def azurite_storage(azurite_settings):
    from apps.documents.storage import get_storage

    return get_storage()
