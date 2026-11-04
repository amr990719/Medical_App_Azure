"""WhatsApp consent: its own service and endpoint, cleared when the phone number changes."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.applications.factories import ApplicationFactory
from apps.audit.models import AuditAction, AuditLog
from apps.common.exceptions import ApplicationNotEditable, PermissionDeniedError, ValidationFailed
from apps.doctors.factories import DoctorFactory
from apps.doctors.models import Doctor
from apps.doctors.services import set_whatsapp_opt_in, update_profile
from apps.reference.constants import ApplicationStatus

pytestmark = pytest.mark.django_db
URL = "/api/v1/profile/notifications/"
PROFILE_URL = "/api/v1/profile/"
MSG_INVALID_PHONE = "رقم الهاتف المحمول غير صحيح"


def audit_entries(doctor):
    return AuditLog.objects.filter(
        action=AuditAction.WHATSAPP_OPT_IN_CHANGED, object_id=doctor.pk
    ).order_by("timestamp")


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def opted_in_doctor(**fields):
    doctor = DoctorFactory(**fields)
    set_whatsapp_opt_in(doctor, enabled=True, actor=doctor.user)
    doctor.refresh_from_db()
    return doctor


# ---- service ----


def test_opt_in_sets_flag_time_and_audit():
    doctor = DoctorFactory()
    result = set_whatsapp_opt_in(doctor, enabled=True, actor=doctor.user)
    doctor.refresh_from_db()
    assert result.whatsapp_opt_in is True
    assert doctor.whatsapp_opt_in is True and doctor.whatsapp_opt_in_at is not None
    entry = audit_entries(doctor).get()
    assert entry.user == doctor.user
    assert entry.metadata == {"enabled": True, "source": "profile"}
    assert doctor.phone_number not in str(entry.metadata)


def test_opt_out_clears_flag_and_time():
    doctor = opted_in_doctor()
    set_whatsapp_opt_in(doctor, enabled=False, actor=doctor.user)
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is False and doctor.whatsapp_opt_in_at is None
    assert audit_entries(doctor).get(metadata__enabled=False).metadata == {
        "enabled": False,
        "source": "profile",
    }


def test_repeating_the_same_value_writes_no_audit():
    doctor = opted_in_doctor()
    first_time = doctor.whatsapp_opt_in_at
    set_whatsapp_opt_in(doctor, enabled=True, actor=doctor.user)
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in_at == first_time
    assert audit_entries(doctor).count() == 1
    other = DoctorFactory()
    set_whatsapp_opt_in(other, enabled=False, actor=other.user)
    assert audit_entries(other).count() == 0


@pytest.mark.parametrize("phone", ["0101", "", "02012345678"])
def test_opt_in_refused_for_incomplete_phone(phone):
    doctor = DoctorFactory(phone_number=phone)
    with pytest.raises(ValidationFailed) as error:
        set_whatsapp_opt_in(doctor, enabled=True, actor=doctor.user)
    assert error.value.fields == {"whatsapp_opt_in": [MSG_INVALID_PHONE]}
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is False
    assert not audit_entries(doctor).exists()


def test_opt_out_allowed_with_an_invalid_phone():
    doctor = opted_in_doctor()
    Doctor.objects.filter(pk=doctor.pk).update(phone_number="0101")
    set_whatsapp_opt_in(doctor, enabled=False, actor=doctor.user)
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is False


def test_opt_in_works_on_a_frozen_profile():
    doctor = DoctorFactory()
    ApplicationFactory(
        doctor=doctor, status=ApplicationStatus.UNDER_REVIEW, reference_number="MED-2026-000001"
    )
    with pytest.raises(ApplicationNotEditable):
        update_profile(doctor, actor=doctor.user, changes={"address": "عنوان جديد"})
    set_whatsapp_opt_in(doctor, enabled=True, actor=doctor.user)
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is True


def test_another_user_cannot_change_it():
    doctor = DoctorFactory()
    for actor in (UserFactory(), None):
        with pytest.raises(PermissionDeniedError):
            set_whatsapp_opt_in(doctor, enabled=True, actor=actor)
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is False


# ---- phone change ----


def test_changing_the_phone_clears_the_opt_in_and_audits():
    doctor = opted_in_doctor()
    update_profile(doctor, actor=doctor.user, changes={"phone_number": "01112345678"})
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is False and doctor.whatsapp_opt_in_at is None
    assert audit_entries(doctor).count() == 2
    assert audit_entries(doctor).get(metadata__enabled=False).metadata == {
        "enabled": False,
        "source": "profile",
    }


def test_clearing_the_phone_clears_the_opt_in():
    doctor = opted_in_doctor()
    update_profile(doctor, actor=doctor.user, changes={"phone_number": ""})
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is False


def test_changing_the_phone_without_opt_in_writes_no_audit():
    doctor = DoctorFactory()
    update_profile(doctor, actor=doctor.user, changes={"phone_number": "01112345678"})
    assert not audit_entries(doctor).exists()


def test_same_number_in_another_form_keeps_the_opt_in():
    doctor = opted_in_doctor(phone_number="01012345678")
    update_profile(doctor, actor=doctor.user, changes={"phone_number": "+201012345678"})
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is True
    assert audit_entries(doctor).count() == 1


def test_saving_other_profile_fields_keeps_the_opt_in():
    doctor = opted_in_doctor()
    update_profile(doctor, actor=doctor.user, changes={"address": "عنوان جديد"})
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is True


def test_serializer_cannot_set_opt_in_through_profile_patch():
    doctor = DoctorFactory()
    response = client_for(doctor.user).patch(
        PROFILE_URL,
        {"whatsapp_opt_in": True, "whatsapp_opt_in_at": "2026-01-01T00:00:00Z"},
        format="json",
    )
    assert response.status_code == 200
    assert "whatsapp_opt_in" not in response.json()
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is False and doctor.whatsapp_opt_in_at is None


# ---- API ----


def test_get_returns_own_state_and_doctor_id():
    doctor = opted_in_doctor()
    data = client_for(doctor.user).get(URL).json()
    assert set(data) == {
        "doctor_id",
        "whatsapp_opt_in",
        "whatsapp_opt_in_at",
        "phone_number",
        "phone_valid",
        "whatsapp_available",
    }
    assert data["doctor_id"] == str(doctor.pk)
    assert data["whatsapp_opt_in"] is True and data["whatsapp_opt_in_at"]
    assert data["phone_number"] == "01012345678" and data["phone_valid"] is True


def test_get_reports_an_invalid_phone():
    doctor = DoctorFactory(phone_number="0101")
    data = client_for(doctor.user).get(URL).json()
    assert data["phone_valid"] is False and data["whatsapp_opt_in"] is False


def test_put_sets_and_returns_the_state():
    doctor = DoctorFactory()
    client = client_for(doctor.user)
    response = client.put(URL, {"whatsapp_opt_in": True}, format="json")
    assert response.status_code == 200
    assert response.json()["whatsapp_opt_in"] is True
    off = client.put(URL, {"whatsapp_opt_in": False}, format="json")
    assert off.json()["whatsapp_opt_in"] is False


def test_put_refused_for_incomplete_phone_uses_the_error_envelope():
    doctor = DoctorFactory(phone_number="0101")
    response = client_for(doctor.user).put(URL, {"whatsapp_opt_in": True}, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["fields"] == {"whatsapp_opt_in": [MSG_INVALID_PHONE]}


def test_put_requires_authentication_and_doctor_role():
    assert APIClient().put(URL, {"whatsapp_opt_in": True}, format="json").status_code == 401
    assert APIClient().get(URL).status_code == 401
    admin = client_for(AdminUserFactory())
    assert admin.put(URL, {"whatsapp_opt_in": True}, format="json").status_code == 403
    assert admin.get(URL).status_code == 403


@pytest.mark.parametrize("body", [{}, {"whatsapp_opt_in": "maybe"}, {"whatsapp_opt_in": None}])
def test_put_rejects_non_boolean(body):
    doctor = DoctorFactory()
    response = client_for(doctor.user).put(URL, body, format="json")
    assert response.status_code == 400
    assert "whatsapp_opt_in" in response.json()["error"]["fields"]


# ---- availability gate ----


@pytest.mark.parametrize("mode,available", [("off", False), ("allowlist", True), ("live", True)])
def test_get_reports_whatsapp_availability(settings, mode, available):
    settings.NOTIFICATIONS_MODE = mode
    doctor = DoctorFactory()
    body = client_for(doctor.user).get(URL).json()
    assert body["whatsapp_available"] is available


def test_opting_in_is_refused_while_whatsapp_is_unavailable(settings):
    settings.NOTIFICATIONS_MODE = "off"
    doctor = DoctorFactory()
    with pytest.raises(ValidationFailed):
        set_whatsapp_opt_in(doctor, enabled=True, actor=doctor.user)
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is False and audit_entries(doctor).count() == 0


def test_the_endpoint_refuses_opt_in_with_a_field_error_while_unavailable(settings):
    settings.NOTIFICATIONS_MODE = "off"
    doctor = DoctorFactory()
    response = client_for(doctor.user).put(URL, {"whatsapp_opt_in": True}, format="json")
    assert response.status_code == 400
    assert "whatsapp_opt_in" in response.json()["error"]["fields"]


def test_opting_out_is_always_allowed(settings):
    doctor = opted_in_doctor()
    settings.NOTIFICATIONS_MODE = "off"
    set_whatsapp_opt_in(doctor, enabled=False, actor=doctor.user)
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is False


def test_sender_and_gate_share_one_definition_of_sending_modes():
    from apps.notifications import sender
    from apps.notifications.modes import SENDING_MODES

    assert sender.SENDING_MODES is SENDING_MODES
