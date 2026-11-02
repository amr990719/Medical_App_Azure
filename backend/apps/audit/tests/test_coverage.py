"""Every §39 audit action is produced by its endpoint/service, and no audit entry carries a
national ID, filename or OCR value (PROMPT.md §39)."""

import re
from io import StringIO

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.audit.models import AuditAction, AuditLog
from apps.beneficiaries.models import Beneficiary
from apps.fees.models import FeeSchedule
from apps.reference.constants import DocumentType as T
from tests.files import png_upload

pytestmark = pytest.mark.django_db

PROFILE = {
    "full_name": "أحمد محمد علي حسن",
    "national_id": "28506150101234",
    "religion": "MUSLIM",
    "phone_number": "01012345678",
    "syndicate_type": "HUMAN_MEDICINE",
    "sub_syndicate": "القاهرة",
    "syndicate_registration_number": "12345",
    "syndicate_registration_year": 2014,
    "governorate": "القاهرة",
    "neighborhood": "مدينة نصر",
    "address": "شارع عباس العقاد",
}


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def upload(client, app_id, doc_type, beneficiary_id=None, size=(800, 600)):
    data = {"file": png_upload(size, name="مستند خاص.png"), "document_type": doc_type}
    if beneficiary_id:
        data["beneficiary_id"] = beneficiary_id
    response = client.post(f"/api/v1/applications/{app_id}/documents/", data, format="multipart")
    assert response.status_code == 201, response.json()
    return response.json()["id"]


@pytest.fixture
def full_lifecycle(settings):
    settings.OCR_ENABLED = True
    doctor_user = UserFactory()
    admin_user = AdminUserFactory()
    doctor, admin = client_for(doctor_user), client_for(admin_user)

    assert doctor.patch("/api/v1/profile/", PROFILE, format="json").status_code == 200
    optin = doctor.put("/api/v1/profile/notifications/", {"whatsapp_opt_in": True}, format="json")
    assert optin.status_code == 200  # WHATSAPP_OPT_IN_CHANGED
    app_id = doctor.post("/api/v1/applications/", {}).json()["id"]  # APPLICATION_CREATED
    base = f"/api/v1/applications/{app_id}/"
    doctor.patch(base, {"work_status": "WORKING", "declaration_name": PROFILE["full_name"],
                        "declaration_accepted": True}, format="json")  # fmt: skip
    front = upload(doctor, app_id, T.NATIONAL_ID_FRONT)
    doctor.post(f"/api/v1/documents/{front}/extract/")  # OCR_REQUESTED
    upload(doctor, app_id, T.NATIONAL_ID_FRONT)  # DOCUMENT_REPLACED
    upload(doctor, app_id, T.NATIONAL_ID_BACK)
    upload(doctor, app_id, T.SYNDICATE_ID)
    extra = upload(doctor, app_id, T.PERSONAL_PHOTO)
    doctor.delete(f"/api/v1/documents/{extra}/")  # DOCUMENT_DELETED
    upload(doctor, app_id, T.PERSONAL_PHOTO)  # required for a FIRST_TIME application
    doctor.get(f"/api/v1/documents/{front}/content/")  # DOCUMENT_VIEWED (replaced → 404)
    wife = doctor.post(f"{base}beneficiaries/", {
        "kinship": "WIFE", "full_name": "سارة محمود علي", "birth_year": 1988,
        "national_id": "28803150101242"}).json()["id"]  # fmt: skip
    for doc_type in (T.BENEFICIARY_NATIONAL_ID, T.BENEFICIARY_NATIONAL_ID_BACK,
                     T.MARRIAGE_CERTIFICATE, T.INSURANCE_PRINT,
                     T.BENEFICIARY_PERSONAL_PHOTO):  # fmt: skip
        upload(doctor, app_id, doc_type, beneficiary_id=wife)
    receipt = upload(doctor, app_id, T.PAYMENT_RECEIPT)  # PAYMENT_STATUS_CHANGED
    doctor.get(f"/api/v1/documents/{receipt}/content/")  # DOCUMENT_VIEWED
    submit = doctor.post(f"{base}submit/")  # APPLICATION_SUBMITTED + FEE_SNAPSHOT_CREATED
    assert submit.status_code == 200, submit.json()

    admin_base = f"/api/v1/admin/applications/{app_id}/"
    admin.get(admin_base)  # ADMIN_APPLICATION_VIEWED
    admin.get(admin_base, {"reveal_national_id": "1"})  # NATIONAL_ID_REVEALED
    admin.post(f"{admin_base}notes/", {"body": "مراجعة أولية"})  # ADMIN_NOTE_ADDED
    admin.post(f"{admin_base}transition/", {"to_status": "NEEDS_CORRECTION",
                                            "review_notes": "يرجى التوضيح"})  # fmt: skip
    assert doctor.post(f"{base}submit/").status_code == 200  # APPLICATION_RESUBMITTED
    dues_url = f"{admin_base}dues-requests/"
    paid = admin.post(dues_url, {"amount": "250", "reason": "سبب المستحقات الخاص"})
    dues_id = paid.json()["dues_requests"][0]["id"]  # DUES_REQUEST_CREATED
    dues_receipt = doctor.post(
        f"{base}dues-requests/{dues_id}/receipts/",
        {"file": png_upload(name="مستند خاص.png")},
        format="multipart",
    )  # DUES_RECEIPT_UPLOADED
    admin.post(f"{dues_url}{dues_id}/review/", {
        "receipt_id": dues_receipt.json()["receipts"][0]["id"], "decision": "REJECTED",
        "reason": "سبب الرفض الخاص"})  # DUES_RECEIPT_REVIEWED  # fmt: skip
    admin.post(f"{dues_url}{dues_id}/cancel/", {"reason": "سبب الإلغاء الخاص"})
    # ^ DUES_REQUEST_CANCELLED
    schedule = FeeSchedule.objects.get(fiscal_year=2026, is_active=True)
    admin.post("/api/v1/admin/fee-schedules/", {
        "fiscal_year": 2026, "tier_fees": schedule.tier_fees, "admin_fee_base": 200,
        "admin_fee_per_beneficiary": 175, "service_fee": 800}, format="json")  # fmt: skip

    promoted = UserFactory(email="new-admin@example.test")
    call_command("grant_admin", promoted.email, stdout=StringIO())  # ADMIN_ROLE_GRANTED
    call_command("revoke_admin", promoted.email, stdout=StringIO())  # ADMIN_ROLE_REVOKED
    return app_id


# Defined by the data-model task; the producer (admin resend) arrives in a later notification
# task, which must delete this exclusion.
NOT_YET_PRODUCED = {AuditAction.NOTIFICATION_RESENT}


@pytest.mark.parametrize("action", [a.value for a in AuditAction if a not in NOT_YET_PRODUCED])
def test_every_audit_action_is_produced(full_lifecycle, action):
    assert AuditLog.objects.filter(action=action).exists(), action


def test_audit_metadata_never_contains_personal_values(full_lifecycle):
    doctor_nid = PROFILE["national_id"]
    wife_nid = Beneficiary.objects.get(kinship="WIFE").national_id
    for entry in AuditLog.objects.all():
        blob = str(entry.metadata)
        assert not re.search(r"\d{14}", blob), entry.action
        assert doctor_nid not in blob and wife_nid not in blob
        assert "مستند خاص" not in blob  # uploaded filename
        assert PROFILE["full_name"] not in blob
        assert "مراجعة أولية" not in blob and "يرجى التوضيح" not in blob  # note texts
        assert "الخاص" not in blob  # dues reason, rejection and cancellation texts


def test_audit_entries_carry_actor_and_hashed_ip(full_lifecycle):
    entry = AuditLog.objects.filter(action=AuditAction.APPLICATION_SUBMITTED).get()
    assert entry.user is not None
    assert re.fullmatch(r"[0-9a-f]{64}", entry.ip_hash)
    assert "127.0.0.1" not in str(entry.metadata)
