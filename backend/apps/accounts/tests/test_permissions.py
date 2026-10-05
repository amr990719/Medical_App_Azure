import pytest
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APIRequestFactory

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import IsAdmin, IsAuthenticatedActive, IsDoctor

pytestmark = pytest.mark.django_db


def request_for(user):
    request = APIRequestFactory().get("/api/v1/x/")
    request.user = user
    return request


@pytest.mark.parametrize(
    ("permission", "anonymous", "doctor", "admin", "inactive"),
    [
        (IsAuthenticatedActive, False, True, True, False),
        (IsDoctor, False, True, False, False),
        (IsAdmin, False, False, True, False),
    ],
)
def test_permission_matrix(permission, anonymous, doctor, admin, inactive):
    check = permission().has_permission
    assert check(request_for(AnonymousUser()), None) is anonymous
    assert check(request_for(UserFactory()), None) is doctor
    assert check(request_for(AdminUserFactory()), None) is admin
    assert check(request_for(UserFactory(is_active=False)), None) is inactive
