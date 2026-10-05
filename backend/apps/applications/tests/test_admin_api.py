"""Admin endpoints (PROMPT.md §24 Admin, §44, §45) and the full status-transition matrix
through the API (§16.2, §42)."""

import itertools

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.factories import AdminUserFactory
from apps.applications.factories import ApplicationFactory, build_submittable_application
from apps.applications.models import AdminNote, InsuranceApplication
from apps.applications.transitions import ALLOWED
from apps.audit.models import AuditAction, AuditLog
from apps.doctors.factories import DoctorFactory
from apps.reference.constants import ApplicationStatus as S
from apps.reference.constants import PaymentStatus
from apps.reference.constants import PaymentStatus as P

pytestmark = pytest.mark.django_db
ADMIN = "/api/v1/admin/"
_seq = itertools.count(1)


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def admin():
    return client_for(AdminUserFactory())


def submitted(status=S.SUBMITTED, payment=P.PENDING_REVIEW, **doctor_fields):
    """An application in `status` (reference number assigned unless DRAFT)."""
    doctor = DoctorFactory(**doctor_fields) if doctor_fields else None
    app = build_submittable_application(**({"doctor": doctor} if doctor else {}))
    reference = None if status == S.DRAFT else f"MED-2026-{next(_seq):06d}"
    InsuranceApplication.objects.filter(pk=app.pk).update(
        status=status,
        payment_status=payment,
        reference_number=reference,
        submitted_at=None if status == S.DRAFT else timezone.now(),
        fee_snapshot=None if status == S.DRAFT else {"total": 3025, "tier": 3},
    )
    app.refresh_from_db()
    return app


def app_url(app, action: str = "") -> str:
    return f"{ADMIN}applications/{app.pk}/" + (f"{action}/" if action else "")


# --- access ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["stats/", "applications/", "doctors/", "fee-schedules/"],
)
def test_doctor_gets_403_on_admin_endpoints(path):
    app = submitted()
    assert client_for(app.doctor.user).get(f"{ADMIN}{path}").status_code == 403
    assert APIClient().get(f"{ADMIN}{path}").status_code == 401


@pytest.mark.parametrize("action", ["", "notes", "audit"])
def test_doctor_gets_403_on_admin_application_routes(action):
    app = submitted()
    assert client_for(app.doctor.user).get(app_url(app, action)).status_code == 403


def test_doctor_cannot_post_admin_transitions_or_payment():
    app = submitted()
    client = client_for(app.doctor.user)
    assert client.post(app_url(app, "transition"), {"to_status": "APPROVED"}).status_code == 403
    assert client.post(app_url(app, "payment"), {"payment_status": "CONFIRMED"}).status_code == 403
    app.refresh_from_db()
    assert (app.status, app.payment_status) == (S.SUBMITTED, P.PENDING_REVIEW)


# --- stats ----------------------------------------------------------------------------------------


def test_stats_counts_per_status_and_pending_receipts(admin):
    submitted(S.SUBMITTED)
    submitted(S.SUBMITTED, payment=P.CONFIRMED)
    submitted(S.UNDER_REVIEW)
    submitted(S.APPROVED, payment=P.CONFIRMED)
    submitted(S.DRAFT, payment=P.NOT_UPLOADED)
    body = admin.get(f"{ADMIN}stats/").json()
    assert body["fiscal_year"] == 2026
    assert body["total"] == 4  # drafts are not submitted applications
    assert body["by_status"]["SUBMITTED"] == 2
    assert body["by_status"]["UNDER_REVIEW"] == 1
    assert body["by_status"]["APPROVED"] == 1
    assert body["by_status"]["DRAFT"] == 1
    assert body["by_payment_status"]["CONFIRMED"] == 2
    assert body["receipts_pending"] == 2


# --- list, filters, search, ordering, pagination ----------------------------------------------


def test_list_rows_mask_national_ids_and_exclude_drafts(admin):
    app = submitted()
    submitted(S.DRAFT)
    rows = admin.get(f"{ADMIN}applications/").json()["results"]
    assert [r["id"] for r in rows] == [str(app.pk)]
    row = rows[0]
    nid = app.doctor.national_id
    assert row["masked_national_id"] == f"{nid[:2]}•••••••••{nid[-3:]}"
    assert nid not in str(rows)
    assert row["doctor_name"] == app.doctor.full_name
    assert row["total"] == 3025
    assert row["reference_number"] == app.reference_number


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"status": "UNDER_REVIEW"}, ["b"]),
        ({"payment_status": "CONFIRMED"}, ["c"]),
        ({"governorate": "الجيزة"}, ["c"]),
        ({"syndicate_type": "PHARMACY"}, ["b"]),
        ({"sub_syndicate": "الإسكندرية"}, ["b"]),
        ({"fiscal_year": "2026"}, ["a", "b", "c"]),
        ({"fiscal_year": "2025"}, []),
    ],
)
def test_filters(admin, params, expected):
    apps = {
        "a": submitted(S.SUBMITTED),
        "b": submitted(S.UNDER_REVIEW, syndicate_type="PHARMACY", sub_syndicate="الإسكندرية"),
        "c": submitted(S.SUBMITTED, payment=P.CONFIRMED, governorate="الجيزة"),
    }
    rows = admin.get(f"{ADMIN}applications/", params).json()["results"]
    by_id = {str(a.pk): k for k, a in apps.items()}
    assert sorted(by_id[r["id"]] for r in rows) == expected


def test_submitted_date_range(admin):
    old, new = submitted(), submitted()
    InsuranceApplication.objects.filter(pk=old.pk).update(
        submitted_at=timezone.now() - timezone.timedelta(days=10)
    )
    from_date = (timezone.localdate() - timezone.timedelta(days=2)).isoformat()
    rows = admin.get(f"{ADMIN}applications/", {"submitted_from": from_date}).json()["results"]
    assert [r["id"] for r in rows] == [str(new.pk)]
    to_date = (timezone.localdate() - timezone.timedelta(days=5)).isoformat()
    rows = admin.get(f"{ADMIN}applications/", {"submitted_to": to_date}).json()["results"]
    assert [r["id"] for r in rows] == [str(old.pk)]


def test_filters_and_search_by_reference_and_masked_id(admin):
    target = submitted(full_name="سامي فؤاد عبد الله", phone_number="01198765432")
    submitted()
    nid = target.doctor.national_id
    for query in (
        target.reference_number,
        target.reference_number.lower(),
        nid,
        "".join("٠١٢٣٤٥٦٧٨٩"[int(d)] for d in nid),  # Eastern Arabic digits
        f"{nid[:2]}•••••••••{nid[-3:]}",
        f"{nid[:2]}*********{nid[-3:]}",
        "فؤاد",
        "01198765432",
        "98765",
    ):
        rows = admin.get(f"{ADMIN}applications/", {"search": query}).json()["results"]
        assert [r["id"] for r in rows] == [str(target.pk)], query


def test_ordering_by_total_and_reference(admin):
    low, high = submitted(), submitted()
    InsuranceApplication.objects.filter(pk=low.pk).update(fee_snapshot={"total": 750})
    InsuranceApplication.objects.filter(pk=high.pk).update(fee_snapshot={"total": 5000})
    rows = admin.get(f"{ADMIN}applications/", {"ordering": "-total"}).json()["results"]
    assert [r["id"] for r in rows] == [str(high.pk), str(low.pk)]
    rows = admin.get(f"{ADMIN}applications/", {"ordering": "reference_number"}).json()["results"]
    assert [r["reference_number"] for r in rows] == sorted(r["reference_number"] for r in rows)


def test_pagination_default_25_max_100(admin):
    doctors = DoctorFactory.create_batch(3)
    for doctor in doctors:
        ApplicationFactory(
            doctor=doctor, status=S.SUBMITTED, reference_number=f"MED-2026-{next(_seq):06d}"
        )
    body = admin.get(f"{ADMIN}applications/", {"page_size": 2}).json()
    assert body["count"] == 3
    assert len(body["results"]) == 2
    assert body["next"]
    from config.api.pagination import StandardPagination

    assert (StandardPagination.page_size, StandardPagination.max_page_size) == (25, 100)
    big = admin.get(f"{ADMIN}applications/", {"page_size": 5000}).json()
    assert len(big["results"]) == 3  # capped at 100, here only 3 exist


# --- detail ---------------------------------------------------------------------------------------


def test_detail_masks_ids_lists_transitions_and_is_audited(admin):
    app = submitted()
    body = admin.get(app_url(app)).json()
    assert body["doctor"]["national_id"] is None
    assert body["doctor"]["masked_national_id"].endswith(app.doctor.national_id[-3:])
    wife = next(b for b in body["beneficiaries"] if b["kinship"] == "WIFE")
    assert wife["national_id"] is None
    assert wife["masked_national_id"] == "28•••••••••242"
    assert body["fee_snapshot"] == {"total": 3025, "tier": 3}
    assert len(body["documents"]) == 9
    assert set(body["allowed_transitions"]) == {"UNDER_REVIEW", "NEEDS_CORRECTION", "REJECTED"}
    viewed = AuditLog.objects.get(action=AuditAction.ADMIN_APPLICATION_VIEWED)
    assert viewed.object_id == app.pk


def test_approve_is_offered_only_with_confirmed_payment(admin):
    pending = submitted(S.UNDER_REVIEW)
    confirmed = submitted(S.UNDER_REVIEW, payment=P.CONFIRMED)
    assert "APPROVED" not in admin.get(app_url(pending)).json()["allowed_transitions"]
    assert "APPROVED" in admin.get(app_url(confirmed)).json()["allowed_transitions"]


def test_reveal_national_id_is_audited(admin):
    app = submitted()
    body = admin.get(app_url(app), {"reveal_national_id": "1"}).json()
    assert body["doctor"]["national_id"] == app.doctor.national_id
    assert next(b for b in body["beneficiaries"] if b["kinship"] == "WIFE")["national_id"] == (
        "28803150101242"
    )
    entry = AuditLog.objects.get(action=AuditAction.NATIONAL_ID_REVEALED)
    assert entry.object_id == app.pk
    assert app.doctor.national_id not in str(entry.metadata)


def test_detail_includes_duplicate_beneficiary_warnings(admin):
    app = submitted()
    assert admin.get(app_url(app)).json()["beneficiary_warnings"] == []
    submitted()  # another member lists the same wife (same national ID)
    body = admin.get(app_url(app)).json()
    assert any("مسجل كمستفيد في طلب آخر" in w for w in body["beneficiary_warnings"])


def test_admin_detail_of_a_draft_is_404(admin):
    assert admin.get(app_url(submitted(S.DRAFT))).status_code == 404


# --- transitions ----------------------------------------------------------------------------------


def test_transition_endpoint_uses_table(admin):
    app = submitted(S.UNDER_REVIEW)  # payment pending
    response = admin.post(app_url(app, "transition"), {"to_status": "APPROVED"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"
    assert response.json()["error"]["message"] == "لا يمكن قبول الطلب قبل تأكيد الدفع"
    app.refresh_from_db()
    assert app.status == S.UNDER_REVIEW
    assert not AuditLog.objects.filter(action=AuditAction.APPLICATION_STATUS_CHANGED).exists()


def test_needs_correction_requires_notes_visible_to_doctor(admin):
    app = submitted()
    response = admin.post(app_url(app, "transition"), {"to_status": "NEEDS_CORRECTION"})
    assert response.status_code == 400
    assert response.json()["error"]["fields"]["review_notes"] == ["يرجى كتابة ملاحظات المراجعة"]
    response = admin.post(
        app_url(app, "transition"),
        {"to_status": "NEEDS_CORRECTION", "review_notes": "صورة البطاقة غير واضحة"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "NEEDS_CORRECTION"
    doctor_view = client_for(app.doctor.user).get(f"/api/v1/applications/{app.pk}/").json()
    assert doctor_view["review_notes"] == "صورة البطاقة غير واضحة"


def test_payment_confirm_then_approve(admin):
    app = submitted()
    assert admin.post(app_url(app, "transition"), {"to_status": "UNDER_REVIEW"}).status_code == 200
    response = admin.post(app_url(app, "payment"), {"payment_status": "CONFIRMED"})
    assert response.status_code == 200
    assert response.json()["payment_status"] == "CONFIRMED"
    response = admin.post(app_url(app, "transition"), {"to_status": "APPROVED"})
    assert response.status_code == 200
    app.refresh_from_db()
    assert (app.status, app.payment_status) == (S.APPROVED, P.CONFIRMED)
    assert app.reviewed_by is not None


def test_payment_reject_with_note_creates_internal_note(admin):
    app = submitted()
    response = admin.post(
        app_url(app, "payment"), {"payment_status": "REJECTED", "note": "المبلغ غير مطابق"}
    )
    assert response.status_code == 200
    note = AdminNote.objects.get(application=app)
    assert note.body == "المبلغ غير مطابق"
    assert AuditLog.objects.filter(action=AuditAction.ADMIN_NOTE_ADDED).count() == 1


@pytest.mark.parametrize("target", ["NOT_UPLOADED", "PENDING_REVIEW", "PAID"])
def test_payment_endpoint_refuses_server_only_or_unknown_states(admin, target):
    app = submitted()
    response = admin.post(app_url(app, "payment"), {"payment_status": target})
    assert response.status_code in (400, 409)
    app.refresh_from_db()
    assert app.payment_status == P.PENDING_REVIEW


ALL = [s.value for s in S]


def _expected_admin(frm: str, to: str) -> int:
    rule = ALLOWED.get((frm, to))
    if rule is None:
        return 409
    if rule.actor_role != "ADMIN":
        return 403
    return 200


@pytest.mark.parametrize(("frm", "to"), list(itertools.product(ALL, ALL)))
def test_admin_transition_matrix(admin, frm, to):
    """Every (from, to) pair through the admin endpoint: allowed ones succeed (notes given,
    payment confirmed), doctor-only ones are 403, everything else is 409 and changes nothing."""
    app = submitted(frm, payment=P.CONFIRMED)
    response = admin.post(app_url(app, "transition"), {"to_status": to, "review_notes": "ملاحظة"})
    expected = 404 if frm == S.DRAFT else _expected_admin(frm, to)
    assert response.status_code == expected, response.json()
    app.refresh_from_db()
    assert app.status == (to if expected == 200 else frm)
    changed = AuditLog.objects.filter(action=AuditAction.APPLICATION_STATUS_CHANGED).exists()
    assert changed is (expected == 200)


@pytest.mark.parametrize("frm", ALL)
def test_doctor_submit_matrix(frm):
    """The doctor's only transition is → SUBMITTED, from DRAFT and NEEDS_CORRECTION."""
    app = submitted(frm, payment=P.PENDING_REVIEW)
    reference = app.reference_number
    response = client_for(app.doctor.user).post(f"/api/v1/applications/{app.pk}/submit/")
    allowed = (frm, S.SUBMITTED) in ALLOWED
    assert response.status_code == (200 if allowed else 409), response.json()
    app.refresh_from_db()
    assert app.status == (S.SUBMITTED if allowed else frm)
    if frm == S.NEEDS_CORRECTION:
        assert app.reference_number == reference  # kept on resubmission
    if frm == S.DRAFT:
        assert app.reference_number is not None  # generated at first submission


# --- notes and audit ------------------------------------------------------------------------------


def test_internal_note_not_visible_to_doctor(admin):
    app = submitted()
    response = admin.post(app_url(app, "notes"), {"body": "اتصلت بالعضو"})
    assert response.status_code == 201
    assert response.json()["body"] == "اتصلت بالعضو"
    notes = admin.get(app_url(app, "notes")).json()
    assert [n["body"] for n in notes] == ["اتصلت بالعضو"]
    doctor_view = client_for(app.doctor.user).get(f"/api/v1/applications/{app.pk}/").json()
    assert "اتصلت بالعضو" not in str(doctor_view)
    assert "admin_notes" not in doctor_view
    assert AuditLog.objects.filter(action=AuditAction.ADMIN_NOTE_ADDED).count() == 1


def test_empty_note_rejected(admin):
    response = admin.post(app_url(submitted(), "notes"), {"body": "   "})
    assert response.status_code == 400


def test_application_audit_history(admin):
    app = submitted()
    admin.post(app_url(app, "transition"), {"to_status": "UNDER_REVIEW"})
    body = admin.get(app_url(app, "audit")).json()
    actions = [e["action"] for e in body["results"]]
    assert "APPLICATION_STATUS_CHANGED" in actions
    entry = next(e for e in body["results"] if e["action"] == "APPLICATION_STATUS_CHANGED")
    assert entry["metadata"] == {"from": "SUBMITTED", "to": "UNDER_REVIEW", "notes": False}
    assert "user_email" in entry


# --- doctors --------------------------------------------------------------------------------------


def test_admin_doctor_list_and_detail(admin):
    app = submitted(full_name="منى سعيد كامل")
    DoctorFactory()
    rows = admin.get(f"{ADMIN}doctors/", {"search": "منى"}).json()["results"]
    assert len(rows) == 1
    assert rows[0]["masked_national_id"].endswith(app.doctor.national_id[-3:])
    assert app.doctor.national_id not in str(rows)
    detail = admin.get(f"{ADMIN}doctors/{app.doctor.pk}/").json()
    assert detail["full_name"] == "منى سعيد كامل"
    assert [a["id"] for a in detail["applications"]] == [str(app.pk)]
    assert "national_id" not in detail


def test_payment_status_value_labels_are_stable():
    assert PaymentStatus.CONFIRMED.label == "مؤكد"
