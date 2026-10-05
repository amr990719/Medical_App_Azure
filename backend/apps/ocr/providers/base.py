from typing import Any, Protocol

from apps.reference.constants import DocumentType


class OcrProviderError(Exception):
    """The provider failed. The message is for logs only and must not contain extracted data."""


class OcrProvider(Protocol):
    name: str

    def extract(
        self, *, image: bytes, content_type: str, document_type: DocumentType
    ) -> dict[str, Any]:
        """Raw fields for `document_type` (keys from `apps.ocr.schemas`), un-normalized."""
        ...
