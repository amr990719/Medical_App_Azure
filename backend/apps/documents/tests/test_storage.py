"""Blob storage abstraction (PROMPT.md §19–20): in-memory for unit tests, Azure Blob for
Azurite/Azure. SAS URLs are read-only and live at most 5 minutes."""

import re
import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest

from apps.documents.azurite import azurite_connection_string
from apps.documents.naming import build_blob_name
from apps.documents.storage import AzureBlobStorage, InMemoryStorage, get_storage
from apps.reference.constants import DocumentType as T

# Azurite's public development account on an unused port: SAS signing is local, nothing is sent.
OFFLINE_CONNECTION = azurite_connection_string(port=1)


# --- naming -------------------------------------------------------------------------------------


def test_blob_name_pattern_for_member_documents():
    app_id = uuid.uuid4()
    name = build_blob_name(app_id, None, T.NATIONAL_ID_FRONT, "jpg")
    assert re.fullmatch(
        rf"applications/{app_id}/doctor/national-id-front-[0-9a-f-]{{36}}\.jpg", name
    )


def test_blob_name_pattern_for_beneficiary_documents():
    app_id, ben_id = uuid.uuid4(), uuid.uuid4()
    name = build_blob_name(app_id, ben_id, T.BENEFICIARY_NATIONAL_ID, "png")
    assert re.fullmatch(
        rf"applications/{app_id}/beneficiaries/{ben_id}/national-id-[0-9a-f-]{{36}}\.png", name
    )


def test_blob_names_are_unique_per_call():
    app_id = uuid.uuid4()
    assert build_blob_name(app_id, None, T.SYNDICATE_ID, "pdf") != build_blob_name(
        app_id, None, T.SYNDICATE_ID, "pdf"
    )


def test_every_document_type_has_a_slug():
    for doc_type in T:
        assert build_blob_name(uuid.uuid4(), None, doc_type, "jpg")


# --- in-memory backend ---------------------------------------------------------------------------


def test_in_memory_roundtrip():
    storage = InMemoryStorage()
    storage.upload("applications/a/doctor/x.png", b"data", content_type="image/png")
    assert storage.exists("applications/a/doctor/x.png")
    assert storage.download("applications/a/doctor/x.png") == b"data"
    assert [b.name for b in storage.list("applications/")] == ["applications/a/doctor/x.png"]
    storage.delete("applications/a/doctor/x.png")
    storage.delete("applications/a/doctor/x.png")  # idempotent
    assert not storage.exists("applications/a/doctor/x.png")
    assert storage.read_url("x", ttl_seconds=60, content_type="image/png", filename="x") is None


def test_in_memory_refuses_overwrite():
    storage = InMemoryStorage()
    storage.upload("n", b"1", content_type="image/png")
    with pytest.raises(FileExistsError):
        storage.upload("n", b"2", content_type="image/png")


def test_test_settings_use_the_shared_in_memory_backend():
    assert isinstance(get_storage(), InMemoryStorage)
    assert get_storage() is get_storage()


# --- SAS ----------------------------------------------------------------------------------------


def sas_params(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def parse_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def test_content_sas_ttl_at_most_300s_and_read_only():
    storage = AzureBlobStorage(connection_string=OFFLINE_CONNECTION, container="medical-documents")
    url = storage.read_url(
        "applications/a/doctor/x.png",
        ttl_seconds=3600,
        content_type="image/png",
        filename="بطاقة.png",
    )
    params = sas_params(url)
    assert urlparse(url).path == "/devstoreaccount1/medical-documents/applications/a/doctor/x.png"
    assert params["sp"] == "r"  # read only
    assert params["sr"] == "b"  # this blob only, never the container
    expiry = parse_time(params["se"])
    remaining = (expiry - datetime.now(UTC)).total_seconds()
    assert 0 < remaining <= 300
    assert params["rsct"] == "image/png"
    assert params["rscd"].startswith("inline")


def test_sas_ttl_shorter_than_maximum_is_respected():
    storage = AzureBlobStorage(connection_string=OFFLINE_CONNECTION, container="medical-documents")
    url = storage.read_url("x.png", ttl_seconds=60, content_type="image/png", filename="x.png")
    remaining = (parse_time(sas_params(url)["se"]) - datetime.now(UTC)).total_seconds()
    assert remaining <= 60


# --- Azurite (real emulator) ---------------------------------------------------------------------


@pytest.mark.azurite
def test_azurite_roundtrip(azurite_storage):
    name = build_blob_name(uuid.uuid4(), None, T.PAYMENT_RECEIPT, "png")
    azurite_storage.upload(name, b"\x89PNG-bytes", content_type="image/png")
    assert azurite_storage.exists(name)
    assert azurite_storage.download(name) == b"\x89PNG-bytes"
    listed = [b for b in azurite_storage.list(name.rsplit("/", 1)[0]) if b.name == name]
    assert listed and listed[0].last_modified.tzinfo is not None
    azurite_storage.delete(name)
    azurite_storage.delete(name)
    assert not azurite_storage.exists(name)
