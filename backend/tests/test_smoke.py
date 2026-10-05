from django.conf import settings
from django.db import connection


def test_database_is_postgresql(db):
    assert connection.vendor == "postgresql"


def test_fiscal_year_setting():
    assert settings.CURRENT_FISCAL_YEAR == 2026


def test_custom_user_model():
    assert settings.AUTH_USER_MODEL == "accounts.User"
