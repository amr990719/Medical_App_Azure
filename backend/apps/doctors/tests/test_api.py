"""`GET/PATCH /api/v1/profile/` — the doctor's own member data (PROMPT.md §12, §13)."""

import threading
from datetime import date

import pytest
from django.db import connection
from rest_framework.test import APIClient

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.applications.factories import ApplicationFactory
from apps.doctors.factories import DoctorFactory
from apps.doctors.models import Doctor
from apps.reference.constants import ApplicationStatus

pytestmark = pytest.mark.django_db
URL = "/api/v1/profile/"
NID_MALE_1985 = "28506150101234"  # born 1985-06-15, governorate 01, digit 13 = 3 → male


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_anonymous_gets_401():
    assert APIClient().get(URL).status_code == 401


def test_admin_cannot_use_the_doctor_profile():
    assert client_for(AdminUserFactory()).get(URL).status_code == 403


def test_get_creates_an_empty_profile_on_first_visit():
    user = UserFactory(email="new@example.test")
    data = client_for(user).get(URL).json()
    assert data["email"] == "new@example.test"
    assert data["full_name"] == ""
    assert data["national_id"] is None
    assert Doctor.objects.filter(user=user).count() == 1


def test_profile_patch_national_id_derives_birth_and_gender():
    user = UserFactory()
    response = client_for(user).patch(URL, {"national_id": NID_MALE_1985}, format="json")
    assert response.status_code == 200
    data = response.json()
    assert data["national_id"] == NID_MALE_1985
    assert data["birth_year"] == 1985
    assert data["date_of_birth"] == "1985-06-15"
    assert data["gender"] == "MALE"
    doctor = Doctor.objects.get(user=user)
    assert doctor.date_of_birth == date(1985, 6, 15)


def test_profile_accepts_arabic_digits():
    user = UserFactory()
    response = client_for(user).patch(
        URL,
        {
            "national_id": "٢٨٥٠٦١٥-٠١٠١٢٣٤",
            "phone_number": "٠١٠ ١٢٣٤ ٥٦٧٨",
            "syndicate_registration_year": "٢٠١٤",
            "syndicate_registration_number": "١٢٣٤٥",
        },
        format="json",
    )
    assert response.status_code == 200, response.json()
    doctor = Doctor.objects.get(user=user)
    assert doctor.national_id == NID_MALE_1985
    assert doctor.phone_number == "01012345678"
    assert doctor.syndicate_registration_year == 2014
    assert doctor.syndicate_registration_number == "12345"


def test_international_phone_is_normalized():
    user = UserFactory()
    client_for(user).patch(URL, {"phone_number": "+20 10 1234 5678"}, format="json")
    assert Doctor.objects.get(user=user).phone_number == "01012345678"


def test_incomplete_phone_is_kept_for_the_draft():
    """Draft level: incomplete is OK; submission validation reports it (rule 7)."""
    user = UserFactory()
    response = client_for(user).patch(URL, {"phone_number": "0101"}, format="json")
    assert response.status_code == 200
    assert Doctor.objects.get(user=user).phone_number == "0101"


def test_phone_with_letters_rejected():
    response = client_for(UserFactory()).patch(URL, {"phone_number": "01x0"}, format="json")
    assert response.status_code == 400
    assert "phone_number" in response.json()["error"]["fields"]


def test_invalid_national_id_rejected_with_arabic_message():
    response = client_for(UserFactory()).patch(URL, {"national_id": "12345"}, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["fields"]["national_id"] == [
        "الرقم القومي يجب أن يكون 14 رقماً صحيحاً"
    ]


def test_gender_conflicting_with_national_id_rejected():
    response = client_for(UserFactory()).patch(
        URL, {"national_id": NID_MALE_1985, "gender": "FEMALE"}, format="json"
    )
    assert response.status_code == 400
    assert response.json()["error"]["fields"]["gender"] == ["يرجى تحديد النوع (ذكر/أنثى)"]


def test_birth_year_conflicting_with_national_id_rejected():
    response = client_for(UserFactory()).patch(
        URL, {"national_id": NID_MALE_1985, "birth_year": 1990}, format="json"
    )
    assert response.status_code == 400
    assert "birth_year" in response.json()["error"]["fields"]


def test_profile_duplicate_national_id_returns_code():
    DoctorFactory(national_id=NID_MALE_1985)
    response = client_for(UserFactory()).patch(URL, {"national_id": NID_MALE_1985}, format="json")
    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "DUPLICATE_NATIONAL_ID",
        "message": "الرقم القومي مسجل لعضو آخر",
        "fields": {"national_id": ["الرقم القومي مسجل لعضو آخر"]},
    }


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_concurrent_duplicate_national_id_one_wins():
    users = [UserFactory(), UserFactory()]
    for user in users:
        DoctorFactory(user=user, national_id=None)
    barrier = threading.Barrier(2)
    statuses = []

    def patch(user):
        try:
            barrier.wait()
            response = client_for(user).patch(URL, {"national_id": NID_MALE_1985}, format="json")
            statuses.append(response.status_code)
        finally:
            connection.close()

    threads = [threading.Thread(target=patch, args=(u,)) for u in users]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(statuses) == [200, 409]
    assert Doctor.objects.filter(national_id=NID_MALE_1985).count() == 1


def test_clearing_national_id_stores_null():
    user = UserFactory()
    DoctorFactory(user=user)
    client_for(user).patch(URL, {"national_id": ""}, format="json")
    assert Doctor.objects.get(user=user).national_id is None


def test_governorate_must_be_one_of_the_27():
    response = client_for(UserFactory()).patch(URL, {"governorate": "باريس"}, format="json")
    assert response.status_code == 400
    assert "governorate" in response.json()["error"]["fields"]


def test_email_and_derived_fields_are_read_only():
    user = UserFactory(email="me@example.test")
    client_for(user).patch(
        URL, {"email": "evil@example.test", "date_of_birth": "2000-01-01"}, format="json"
    )
    user.refresh_from_db()
    assert user.email == "me@example.test"
    assert Doctor.objects.get(user=user).date_of_birth is None


@pytest.mark.parametrize(
    "status",
    [ApplicationStatus.SUBMITTED, ApplicationStatus.UNDER_REVIEW, ApplicationStatus.APPROVED],
)
def test_profile_locked_while_submitted(status):
    doctor = DoctorFactory(full_name="الاسم الأصلي للعضو")
    ApplicationFactory(doctor=doctor, status=status, reference_number="MED-2026-000001")
    response = client_for(doctor.user).patch(URL, {"full_name": "اسم آخر تماما"}, format="json")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "APPLICATION_NOT_EDITABLE"
    doctor.refresh_from_db()
    assert doctor.full_name == "الاسم الأصلي للعضو"


@pytest.mark.parametrize(
    "status",
    [ApplicationStatus.DRAFT, ApplicationStatus.NEEDS_CORRECTION, ApplicationStatus.REJECTED],
)
def test_profile_editable_while_application_editable_or_rejected(status):
    doctor = DoctorFactory()
    reference = None if status == ApplicationStatus.DRAFT else "MED-2026-000001"
    ApplicationFactory(doctor=doctor, status=status, reference_number=reference)
    response = client_for(doctor.user).patch(URL, {"full_name": "اسم جديد للعضو"}, format="json")
    assert response.status_code == 200


def test_names_are_whitespace_collapsed():
    user = UserFactory()
    client_for(user).patch(URL, {"full_name": "  أحمد   محمد  علي "}, format="json")
    assert Doctor.objects.get(user=user).full_name == "أحمد محمد علي"
