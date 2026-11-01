"""Dues endpoints: admin create / review / cancel on `/admin/applications/{id}/dues-requests/`,
member receipt upload on `/applications/{id}/dues-requests/{dues_id}/receipts/`, and the
read models on both application details."""

import itertools
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.factories import AdminUserFactory
from apps.applications.factories import build_submittable_application
from apps.applications.models import InsuranceApplication
from apps.audit.models import AuditAction
from apps.documents.models import Document
from apps.documents.services import store_document
from apps.documents.storage import get_storage
from apps.dues import services
from apps.dues.models import SyndicateDuesRequest
from apps.reference.constants import ApplicationStatus as S
from apps.reference.constants import DocumentType as T
from apps.reference.constants import DuesReceiptStatus as RS
from apps.reference.constants import PaymentStatus as P
from tests.files import EXE_BYTES, png_upload, upload

pytestmark = pytest.mark.django_db
_seq = itertools.count(900)
ADMIN = "/api/v1/admin/applications/"


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def app_in(status=S.UNDER_REVIEW, payment=P.CONFIRMED):
    app = build_submittable_application()
    InsuranceApplication.objects.filter(pk=app.pk).update(
        status=status,
        payment_status=payment,
        reference_number=None if status == S.DRAFT else f"MED-2026-{next(_seq):06d}",
        submitted_at=None if status == S.DRAFT else timezone.now(),
        fee_snapshot=None if status == S.DRAFT else {"total": 4835, "tier": 3},
    )
    app.refresh_from_db()
    return app


@pytest.fixture
def admin_user():
    return AdminUserFactory()


@pytest.fixture
def admin(admin_user):
    return client_for(admin_user)


def create_url(app):
    return f"{ADMIN}{app.pk}/dues-requests/"


def action_url(dues, action):
    return f"{ADMIN}{dues.application_id}/dues-requests/{dues.pk}/{action}/"


def receipt_url(dues):
    return f"/api/v1/applications/{dues.application_id}/dues-requests/{dues.pk}/receipts/"


def doctor_upload(dues, client=None, file=None):
    client = client or client_for(dues.application.doctor.user)
    return client.post(receipt_url(dues), {"file": file or png_upload()}, format="multipart")


def make_request(app, admin_user, amount="250.00"):
    return services.create_dues_request(
        app, amount=Decimal(amount), reason="اشتراك النقابة", actor=admin_user
    )


# --- admin: create ------------------------------------------------------------------------------


def test_admin_creates_a_request_and_gets_the_detail(admin):
    app = app_in()
    response = admin.post(create_url(app), {"amount": "350.5", "reason": " اشتراك 2026 "})
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["status"] == S.UNDER_REVIEW  # unchanged
    assert body["outstanding_dues_count"] == 1
    assert S.APPROVED not in body["allowed_transitions"]
    [dues] = body["dues_requests"]
    assert dues["amount"] == "350.50"
    assert dues["reason"] == "اشتراك 2026"
    assert dues["status"] == "REQUESTED"
    assert dues["allowed_actions"] == ["CANCEL"]
    assert dues["receipts"] == []
    assert dues["created_by_email"]


@pytest.mark.parametrize(
    ("raw", "stored"),
    [("٢٥٠", "250.00"), ("١٢٥٫٧٥", "125.75"), (300, "300.00"), ("40.5", "40.50")],
)
def test_amount_accepts_arabic_digits_and_numbers(admin, raw, stored):
    app = app_in()
    response = admin.post(create_url(app), {"amount": raw, "reason": "اشتراك"})
    assert response.status_code == 201, response.json()
    assert response.json()["dues_requests"][0]["amount"] == stored


@pytest.mark.parametrize("raw", ["0", "-1", "abc", "", "1e3", "1,000", "99.999", "100000000"])
def test_invalid_amounts_are_refused_in_arabic(admin, raw):
    app = app_in()
    response = admin.post(create_url(app), {"amount": raw, "reason": "اشتراك"})
    assert response.status_code == 400
    assert response.json()["error"]["fields"]["amount"]
    assert not SyndicateDuesRequest.objects.exists()


def test_reason_required(admin):
    response = admin.post(create_url(app_in()), {"amount": "100", "reason": "  "})
    assert response.status_code == 400
    assert response.json()["error"]["fields"]["reason"]


@pytest.mark.parametrize("status", [S.APPROVED, S.REJECTED])
def test_create_refused_for_terminal_applications(admin, status):
    app = app_in(status)
    response = admin.post(create_url(app), {"amount": "100", "reason": "اشتراك"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_draft_is_not_visible_to_admins(admin):
    response = admin.post(create_url(app_in(S.DRAFT)), {"amount": "100", "reason": "اشتراك"})
    assert response.status_code == 404


def test_doctor_cannot_use_admin_dues_routes(admin_user):
    app = app_in()
    dues = make_request(app, admin_user)
    doctor = client_for(app.doctor.user)
    assert doctor.post(create_url(app), {"amount": "1", "reason": "x"}).status_code == 403
    assert doctor.post(action_url(dues, "cancel"), {"reason": "x"}).status_code == 403
    assert doctor.post(action_url(dues, "review"), {"decision": "CONFIRMED"}).status_code == 403


def test_detail_reports_whether_dues_can_be_requested(admin):
    assert admin.get(f"{ADMIN}{app_in(S.UNDER_REVIEW).pk}/").json()["can_request_dues"] is True
    assert admin.get(f"{ADMIN}{app_in(S.APPROVED).pk}/").json()["can_request_dues"] is False


# --- member: upload -----------------------------------------------------------------------------


def test_member_sees_the_request_and_uploads_a_receipt(admin_user):
    app = app_in()
    dues = make_request(app, admin_user)
    client = client_for(app.doctor.user)
    [shown] = client.get(f"/api/v1/applications/{app.pk}/").json()["dues_requests"]
    assert shown["amount"] == "250.00"
    assert shown["reason"] == "اشتراك النقابة"
    assert shown["can_upload_receipt"] is True
    assert "created_by_email" not in shown and "cancellation_reason" not in shown

    response = doctor_upload(dues, client)
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["status"] == "PENDING_REVIEW"
    assert body["can_upload_receipt"] is False
    [receipt] = body["receipts"]
    assert receipt["status"] == "PENDING_REVIEW"
    assert receipt["document"]["content_url"].startswith("/api/v1/documents/")
    assert "reviewed_by_email" not in receipt

    # the receipt is viewable through the authorized endpoint, by the member and by admins
    content = receipt["document"]["content_url"]
    assert client.get(content).status_code == 200
    assert client_for(admin_user).get(content).status_code == 200


def test_receipt_upload_is_not_a_form_document(admin_user):
    app = app_in()
    dues = make_request(app, admin_user)
    doctor_upload(dues)
    client = client_for(app.doctor.user)
    body = client.get(f"/api/v1/applications/{app.pk}/").json()
    assert all(d["document_type"] != T.SYNDICATE_DUES_RECEIPT for d in body["documents"])
    assert body["payment_status"] == P.CONFIRMED
    detail = client_for(admin_user).get(f"{ADMIN}{app.pk}/").json()
    assert all(d["document_type"] != T.SYNDICATE_DUES_RECEIPT for d in detail["documents"])


def test_other_doctor_gets_404(admin_user):
    dues = make_request(app_in(), admin_user)
    stranger = client_for(build_submittable_application().doctor.user)
    assert doctor_upload(dues, stranger).status_code == 404
    assert admin_user and not dues.receipts.exists()


def test_admin_cannot_upload_for_the_member(admin_user, admin):
    dues = make_request(app_in(), admin_user)
    assert doctor_upload(dues, admin).status_code == 403


def test_dues_id_must_belong_to_the_application(admin_user):
    dues = make_request(app_in(), admin_user)
    own_other_app = build_submittable_application(doctor=dues.application.doctor, fiscal_year=2025)
    url = f"/api/v1/applications/{own_other_app.pk}/dues-requests/{dues.pk}/receipts/"
    response = client_for(dues.application.doctor.user).post(
        url, {"file": png_upload()}, format="multipart"
    )
    assert response.status_code == 404


def test_upload_is_validated_like_every_receipt(admin_user):
    dues = make_request(app_in(), admin_user)
    assert doctor_upload(dues, file=upload(EXE_BYTES, "x.png")).status_code == 415
    small = doctor_upload(dues, file=png_upload(size=(300, 200)))
    assert small.status_code == 400
    assert small.json()["error"]["code"] == "IMAGE_TOO_SMALL"
    assert not dues.receipts.exists()


def test_upload_while_pending_is_refused(admin_user):
    dues = make_request(app_in(), admin_user)
    assert doctor_upload(dues).status_code == 201
    response = doctor_upload(dues)
    assert response.status_code == 409
    assert response.json()["error"]["message"] == services.MSG_UPLOAD_NOT_ALLOWED


# --- the full flow over HTTP ----------------------------------------------------------------------


def test_reject_reupload_confirm_then_approve(admin, admin_user):
    app = app_in(S.UNDER_REVIEW, payment=P.CONFIRMED)
    detail = admin.post(create_url(app), {"amount": "200", "reason": "اشتراك"}).json()
    dues = SyndicateDuesRequest.objects.get(pk=detail["dues_requests"][0]["id"])
    member = client_for(app.doctor.user)

    first = doctor_upload(dues, member).json()["receipts"][0]["id"]
    review = action_url(dues, "review")
    no_reason = admin.post(review, {"receipt_id": first, "decision": "REJECTED"})
    assert no_reason.status_code == 400
    assert no_reason.json()["error"]["fields"]["reason"]
    rejected = admin.post(
        action_url(dues, "review"),
        {"receipt_id": first, "decision": "REJECTED", "reason": "المبلغ غير مطابق"},
    )
    assert rejected.status_code == 200, rejected.json()

    [shown] = member.get(f"/api/v1/applications/{app.pk}/").json()["dues_requests"]
    assert shown["status"] == "REJECTED"
    assert shown["can_upload_receipt"] is True
    assert shown["receipts"][0]["rejection_reason"] == "المبلغ غير مطابق"

    second = doctor_upload(dues, member).json()
    assert [r["status"] for r in second["receipts"]] == ["REJECTED", "PENDING_REVIEW"]
    second_id = second["receipts"][1]["id"]

    blocked = admin.post(f"{ADMIN}{app.pk}/transition/", {"to_status": "APPROVED"})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["message"] == services.MSG_DUES_OUTSTANDING

    confirmed = admin.post(
        action_url(dues, "review"), {"receipt_id": second_id, "decision": "CONFIRMED"}
    ).json()
    [row] = confirmed["dues_requests"]
    assert row["status"] == "CONFIRMED"
    assert row["allowed_actions"] == []
    assert row["resolved_by_email"] == admin_user.email
    assert [r["status"] for r in row["receipts"]] == ["REJECTED", "CONFIRMED"]
    assert row["receipts"][0]["reviewed_by_email"] == admin_user.email
    assert confirmed["outstanding_dues_count"] == 0
    assert S.APPROVED in confirmed["allowed_transitions"]

    approved = admin.post(f"{ADMIN}{app.pk}/transition/", {"to_status": "APPROVED"})
    assert approved.status_code == 200
    app.refresh_from_db()
    assert app.status == S.APPROVED
    assert app.payment_status == P.CONFIRMED
    assert app.fee_snapshot == {"total": 4835, "tier": 3}

    actions = {e["action"] for e in admin.get(f"{ADMIN}{app.pk}/audit/").json()["results"]}
    assert {
        AuditAction.DUES_REQUEST_CREATED,
        AuditAction.DUES_RECEIPT_UPLOADED,
        AuditAction.DUES_RECEIPT_REVIEWED,
        AuditAction.DOCUMENT_UPLOADED,
    } <= actions


def test_review_with_a_stale_receipt_id_is_refused(admin, admin_user):
    dues = make_request(app_in(), admin_user)
    first = doctor_upload(dues).json()["receipts"][0]["id"]
    review = action_url(dues, "review")
    admin.post(review, {"receipt_id": first, "decision": "REJECTED", "reason": "غير واضح"})
    doctor_upload(dues)
    response = admin.post(review, {"receipt_id": first, "decision": "CONFIRMED"})
    assert response.status_code == 409


def test_cancel_needs_a_reason_and_unblocks_approval(admin, admin_user):
    app = app_in(S.UNDER_REVIEW, payment=P.CONFIRMED)
    dues = make_request(app, admin_user)
    assert admin.post(action_url(dues, "cancel"), {"reason": ""}).status_code == 400
    response = admin.post(action_url(dues, "cancel"), {"reason": "سُدد مباشرة"})
    assert response.status_code == 200
    [row] = response.json()["dues_requests"]
    assert row["status"] == "CANCELLED"
    assert row["cancellation_reason"] == "سُدد مباشرة"
    assert S.APPROVED in response.json()["allowed_transitions"]
    [shown] = (
        client_for(app.doctor.user).get(f"/api/v1/applications/{app.pk}/").json()["dues_requests"]
    )
    assert shown["status"] == "CANCELLED"
    assert shown["can_upload_receipt"] is False


def test_dues_of_another_application_are_404(admin, admin_user):
    dues = make_request(app_in(), admin_user)
    other = app_in()
    url = f"{ADMIN}{other.pk}/dues-requests/{dues.pk}/cancel/"
    assert admin.post(url, {"reason": "x"}).status_code == 404


# --- separation from the form documents -------------------------------------------------------


def test_generic_document_upload_refuses_the_dues_type():
    app = build_submittable_application()
    response = client_for(app.doctor.user).post(
        f"/api/v1/applications/{app.pk}/documents/",
        {"file": png_upload(), "document_type": "SYNDICATE_DUES_RECEIPT"},
        format="multipart",
    )
    assert response.status_code == 400
    assert response.json()["error"]["fields"]["document_type"]


def test_dues_receipt_cannot_be_deleted_even_while_editable(admin_user):
    app = app_in(S.NEEDS_CORRECTION)
    dues = make_request(app, admin_user)
    receipt_id = doctor_upload(dues).json()["receipts"][0]["document"]["id"]
    response = client_for(app.doctor.user).delete(f"/api/v1/documents/{receipt_id}/")
    assert response.status_code == 403
    assert Document.objects.filter(pk=receipt_id).exists()


def test_form_slot_replacement_still_replaces(admin_user):
    app = build_submittable_application()
    first = store_document(
        app, document_type=T.SYNDICATE_ID, upload=png_upload(), actor=app.doctor.user
    )
    store_document(app, document_type=T.SYNDICATE_ID, upload=png_upload(), actor=app.doctor.user)
    first.refresh_from_db()
    assert first.deleted_at is not None


def test_cleanup_job_keeps_dues_receipt_blobs(admin_user):
    dues = make_request(app_in(), admin_user)
    receipt = services.submit_dues_receipt(
        dues, upload=png_upload(), actor=dues.application.doctor.user
    )
    storage = get_storage()
    later = timezone.now() + timedelta(days=30)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(timezone, "now", lambda: later)
        call_command("cleanup_blobs", grace_hours=0)
    assert storage.download(receipt.document.blob_name)
    assert receipt.status == RS.PENDING_REVIEW


def test_reference_data_lists_the_dues_statuses():
    app = build_submittable_application()
    body = client_for(app.doctor.user).get("/api/v1/reference-data/").json()
    assert {c["value"] for c in body["dues_request_statuses"]} == {
        "REQUESTED", "PENDING_REVIEW", "REJECTED", "CONFIRMED", "CANCELLED",
    }  # fmt: skip
    assert {c["value"] for c in body["dues_receipt_statuses"]} == {
        "PENDING_REVIEW", "CONFIRMED", "REJECTED", "CANCELLED",
    }  # fmt: skip
