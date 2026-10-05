from django.conf import settings

from .base import OcrProvider, OcrProviderError


def get_provider() -> OcrProvider:
    """Provider selected by OCR_PROVIDER ("mock" | "azure_openai")."""
    if settings.OCR_PROVIDER == "mock":
        from .mock import MockOcrProvider

        return MockOcrProvider()
    if settings.OCR_PROVIDER == "azure_openai":
        from .azure_openai import AzureOpenAIProvider

        return AzureOpenAIProvider()
    raise OcrProviderError("unknown OCR provider")


__all__ = ["OcrProvider", "OcrProviderError", "get_provider"]
