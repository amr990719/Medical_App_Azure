import pytest

from apps.notifications import providers


@pytest.fixture(autouse=True)
def _reset_provider_caches():
    """Fakes and the SES client are cached; start every test clean."""
    providers.get_whatsapp_client.cache_clear()
    providers.get_email_client.cache_clear()
    providers._ses_client.cache_clear()
    yield
    providers.get_whatsapp_client.cache_clear()
    providers.get_email_client.cache_clear()
    providers._ses_client.cache_clear()
