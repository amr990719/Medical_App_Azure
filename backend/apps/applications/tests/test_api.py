"""Doctor application endpoints (PROMPT.md §24) incl. IDOR and protected-field attempts (§28)."""

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.applications.factories import ApplicationFactory, build_submittable_application
from apps.applications.models import InsuranceApplication
from apps.audit.models import AuditAction, AuditLog
from apps.beneficiaries.factories import BeneficiaryFactory
from apps.doctors.factories import DoctorFactory
from apps.doctors.models import Doctor
from apps.fees.models import FeeSchedule
from apps.reference.constants import ApplicationStatus as S
from apps.reference.constants import ApplicationType, PaymentStatus, WorkStatus

pytestmark = pytest.mark.django_db
BASE = "/api/v1/applications/"


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def url(app, action: str = "") -> str:
    return f"{BASE}{app.pk}/" + (f"{action}/" if action else "")


# --- list / create / retrieve ------------------------------------------------------------------


def test_anonymous_gets_401():
    assert APIClient().get(BASE).status_code == 401


def test_doctor_sees_only_own_applications():
    mine = ApplicationFactory()
    ApplicationFactory()  # another doctor's
    data = client_for(mine.doctor.user).get(BASE).json()
    assert [row["id"] for row in data["results"]] == [str(mine.pk)]


def test_create_draft_returns_201_and_creates_the_profile():
    user = UserFactory()
    response = client_for(user).post(BASE, {}, format="json")
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["fiscal_year"] == 2026
    assert body["reference_number"] is None
    assert body["is_editable"] is True
    assert Doctor.objects.filter(user=user).exists()
    assert AuditLog.objects.filter(action=AuditAction.APPLICATION_CREATED).count() == 1


def test_create_twice_returns_same_draft():
    user = UserFactory()
    client = client_for(user)
    first = client.post(BASE, {}, format="json")
    second = client.post(BASE, {}, format="json")
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert InsuranceApplication.objects.count() == 1


def test_create_after_rejection_starts_a_new_application():
    old = ApplicationFactory(status=S.REJECTED, reference_number="MED-2026-000009")
    response = client_for(old.doctor.user).post(BASE, {"application_type": "ADDITION"})
    assert response.status_code == 201
    assert response.json()["application_type"] == ApplicationType.ADDITION
    assert response.json()["id"] != str(old.pk)


def test_create_cannot_choose_fiscal_year_or_status():
    user = UserFactory()
    body = (
        client_for(user)
        .post(
            BASE, {"fiscal_year": 2030, "status": "APPROVED", "reference_number": "MED-2030-000001"}
        )
        .json()
    )
    assert body["fiscal_year"] == 2026
    assert body["status"] == "DRAFT"
    assert body["reference_number"] is None


def test_retrieve_includes_nested_beneficiaries_and_documents():
    app = build_submittable_application()
    body = client_for(app.doctor.user).get(url(app)).json()
    assert [b["row_number"] for b in body["beneficiaries"]] == [1, 2, 3]
    assert body["beneficiaries"][0]["kinship"] == "WIFE"
    required = {r["type"] for r in body["beneficiaries"][0]["required_documents"]}
    assert required == {"BENEFICIARY_NATIONAL_ID", "MARRIAGE_CERTIFICATE", "INSURANCE_PRINT"}
    assert len(body["documents"]) == 9
    doc = body["documents"][0]
    assert doc["content_url"] == f"/api/v1/documents/{doc['id']}/content/"
    assert "blob_name" not in doc
    assert "submitted_snapshot" not in body


# --- IDOR on every doctor route ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "action"),
    [("get", ""), ("patch", ""), ("get", "fees"), ("get", "validation"), ("post", "submit")],
)
def test_other_doctors_application_is_404_on_every_route(method, action):
    victim = build_submittable_application()
    attacker = DoctorFactory().user
    response = getattr(client_for(attacker), method)(url(victim, action), {}, format="json")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    victim.refresh_from_db()
    assert victim.status == S.DRAFT


@pytest.mark.parametrize(
    ("method", "action"), [("get", ""), ("get", "fees"), ("post", "submit"), ("get", None)]
)
def test_admin_cannot_use_doctor_endpoints_for_others(method, action):
    app = build_submittable_application()
    target = BASE if action is None else url(app, action)
    response = getattr(client_for(AdminUserFactory()), method)(target, {}, format="json")
    assert response.status_code == 403
    app.refresh_from_db()
    assert app.status == S.DRAFT


def test_malformed_id_is_404():
    assert client_for(UserFactory()).get(f"{BASE}not-a-uuid/").status_code == 404


# --- PATCH --------------------------------------------------------------------------------------


def test_patch_editable_fields():
    app = ApplicationFactory(work_status="")
    response = client_for(app.doctor.user).patch(
        url(app),
        {
            "work_status": "PENSIONER",
            "declaration_name": "  أحمد   محمد علي حسن ",
            "declaration_accepted": True,
            "application_type": "ADDITION",
        },
        format="json",
    )
    assert response.status_code == 200, response.json()
    app.refresh_from_db()
    assert app.work_status == WorkStatus.PENSIONER
    assert app.declaration_name == "أحمد محمد علي حسن"
    assert app.declaration_accepted_at is not None
    assert app.application_type == ApplicationType.ADDITION
    assert response.json()["declaration_accepted"] is True


def test_withdrawing_declaration_clears_the_acceptance_time():
    app = ApplicationFactory(declaration_accepted_at=timezone.now())
    client_for(app.doctor.user).patch(url(app), {"declaration_accepted": False}, format="json")
    app.refresh_from_db()
    assert app.declaration_accepted_at is None


def test_invalid_enum_rejected():
    app = ApplicationFactory()
    response = client_for(app.doctor.user).patch(url(app), {"work_status": "RETIRED"})
    assert response.status_code == 400
    assert "work_status" in response.json()["error"]["fields"]


PROTECTED = {
    "status": "APPROVED",
    "payment_status": "CONFIRMED",
    "reference_number": "MED-2026-999999",
    "fee_snapshot": {"total": 1},
    "fee_schedule": None,
    "review_notes": "self-approved",
    "reviewed_at": "2026-01-01T00:00:00Z",
    "submitted_at": "2026-01-01T00:00:00Z",
    "submitted_snapshot": {"member": {}},
    "fiscal_year": 2030,
    "doctor": None,
    "declaration_accepted_at": "2020-01-01T00:00:00Z",
}


@pytest.mark.parametrize("field", sorted(PROTECTED))
def test_patch_protected_fields_ignored(field):
    app = ApplicationFactory()
    before = InsuranceApplication.objects.filter(pk=app.pk).values().get()
    response = client_for(app.doctor.user).patch(url(app), {field: PROTECTED[field]}, format="json")
    assert response.status_code == 200
    after = InsuranceApplication.objects.filter(pk=app.pk).values().get()
    before.pop("updated_at")
    after.pop("updated_at")
    assert after == before


def test_patch_protected_payment_status_on_submitted_app_is_refused_and_unchanged():
    app = build_submittable_application()
    client = client_for(app.doctor.user)
    client.post(url(app, "submit"))
    response = client.patch(url(app), {"payment_status": "CONFIRMED"}, format="json")
    assert response.status_code == 409
    app.refresh_from_db()
    assert app.payment_status == PaymentStatus.PENDING_REVIEW


@pytest.mark.parametrize("status", [S.SUBMITTED, S.UNDER_REVIEW, S.APPROVED, S.REJECTED])
def test_patch_when_not_editable_returns_409_and_no_audit(status):
    app = ApplicationFactory(status=status, reference_number="MED-2026-000001")
    audit_before = AuditLog.objects.count()
    response = client_for(app.doctor.user).patch(
        url(app), {"declaration_name": "تغيير"}, format="json"
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "APPLICATION_NOT_EDITABLE"
    assert AuditLog.objects.count() == audit_before
    app.refresh_from_db()
    assert app.declaration_name == ""


def test_patch_requires_csrf_for_session_clients():
    app = ApplicationFactory()
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(app.doctor.user, backend="apps.accounts.backends.SessionOnlyBackend")
    response = client.patch(url(app), {"work_status": "PENSIONER"}, format="json")
    assert response.status_code == 403


# --- fees / validation --------------------------------------------------------------------------


def test_fees_endpoint_matches_example_2():
    app = build_submittable_application()
    body = client_for(app.doctor.user).get(url(app, "fees")).json()
    assert body["total"] == 3025
    assert body["tier"] == 3
    assert body["is_valid"] is True
    assert [line["fee"] for line in body["breakdown"]] == [750, 1000, 550, 550, 175]
    assert body["schedule_id"] == str(FeeSchedule.objects.get(fiscal_year=2026, version=1).pk)


def test_fees_invalid_registration_year_is_reported_not_raised():
    doctor = DoctorFactory(syndicate_registration_year=None)
    app = ApplicationFactory(doctor=doctor)
    body = client_for(doctor.user).get(url(app, "fees")).json()
    assert body["is_valid"] is False
    assert body["total"] == 0


def test_fees_of_a_submitted_application_are_the_frozen_snapshot():
    app = ApplicationFactory(
        status=S.SUBMITTED,
        reference_number="MED-2026-000001",
        fee_snapshot={"fiscal_year": 2026, "tier": 1, "breakdown": [], "admin_fee": 150,
                      "total": 9999, "is_valid": True, "error_message": "", "schedule_id": ""},
    )  # fmt: skip
    assert client_for(app.doctor.user).get(url(app, "fees")).json()["total"] == 9999


def test_validation_endpoint_groups_by_step():
    doctor = DoctorFactory(phone_number="123")
    app = ApplicationFactory(doctor=doctor)
    body = client_for(doctor.user).get(url(app, "validation")).json()
    assert body["is_valid"] is False
    assert body["submit_ready"] is False
    assert set(body["by_step"]) == {"1", "2", "3", "4", "5"}
    step1 = {e["field"] for e in body["by_step"]["1"]}
    assert "member.phone_number" in step1
    assert any(e["code"] == "MISSING_DOCUMENT" for e in body["by_step"]["3"])
    assert body["by_step"]["4"] == []  # receipt is submit-only: not an error while drafting
    assert body["steps_complete"]["4"] is False


def test_validation_ready_application():
    app = build_submittable_application()
    body = client_for(app.doctor.user).get(url(app, "validation")).json()
    assert body["is_valid"] is True
    assert body["submit_ready"] is True


# --- submit -------------------------------------------------------------------------------------


def test_submit_happy_path_returns_reference():
    app = build_submittable_application()
    response = client_for(app.doctor.user).post(url(app, "submit"))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUBMITTED"
    assert body["reference_number"] == "MED-2026-000001"
    assert body["fee_snapshot"]["total"] == 3025
    assert body["is_editable"] is False


def test_submit_errors_return_every_message_grouped_by_step():
    doctor = DoctorFactory(phone_number="123", full_name="أحمد")
    app = ApplicationFactory(doctor=doctor)
    response = client_for(doctor.user).post(url(app, "submit"))
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    steps = {e["step"] for e in error["errors"]}
    assert {1, 3, 4, 5} <= steps
    messages = [m for msgs in error["fields"].values() for m in msgs]
    assert "رقم الهاتف المحمول غير صحيح" in messages
    assert "يرجى رفع إيصال الدفع" in messages
    assert "يرجى الموافقة على الإقرار" in messages
    app.refresh_from_db()
    assert app.status == S.DRAFT
    assert app.reference_number is None


def test_submit_twice_is_an_invalid_transition():
    app = build_submittable_application()
    client = client_for(app.doctor.user)
    client.post(url(app, "submit"))
    response = client.post(url(app, "submit"))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_resubmit_after_needs_correction_keeps_reference_number():
    app = build_submittable_application()
    client = client_for(app.doctor.user)
    first = client.post(url(app, "submit")).json()["reference_number"]
    InsuranceApplication.objects.filter(pk=app.pk).update(
        status=S.NEEDS_CORRECTION, review_notes="صورة البطاقة غير واضحة"
    )
    assert client.get(url(app)).json()["review_notes"] == "صورة البطاقة غير واضحة"
    assert client.patch(url(app), {"work_status": "WORKING"}).status_code == 200
    response = client.post(url(app, "submit"))
    assert response.status_code == 200
    assert response.json()["status"] == "SUBMITTED"
    assert response.json()["reference_number"] == first
    assert AuditLog.objects.filter(action=AuditAction.APPLICATION_RESUBMITTED).count() == 1


def test_detail_query_count_does_not_grow_with_beneficiaries(django_assert_max_num_queries):
    """Nested beneficiaries/documents are prefetched: no N+1 in the serializers."""
    small = build_submittable_application()
    client = client_for(small.doctor.user)
    with django_assert_max_num_queries(10) as small_ctx:
        client.get(url(small))
    big = build_submittable_application(doctor=DoctorFactory())
    for row in range(4, 10):
        BeneficiaryFactory(application=big, row_number=row, kinship="DAUGHTER", full_name="ابنة")
    client = client_for(big.doctor.user)
    with django_assert_max_num_queries(10) as big_ctx:
        client.get(url(big))
    assert len(big_ctx.captured_queries) == len(small_ctx.captured_queries)
