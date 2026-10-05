"""`/api/v1/applications/{id}/beneficiaries/` (PROMPT.md §14, §24)."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.factories import AdminUserFactory
from apps.applications.factories import ApplicationFactory
from apps.beneficiaries.factories import BeneficiaryFactory
from apps.beneficiaries.models import Beneficiary
from apps.doctors.factories import DoctorFactory
from apps.documents.factories import DocumentFactory
from apps.documents.models import Document
from apps.reference.constants import ApplicationStatus as S
from apps.reference.constants import DocumentType, Kinship

pytestmark = pytest.mark.django_db


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def collection(app) -> str:
    return f"/api/v1/applications/{app.pk}/beneficiaries/"


def item(app, beneficiary) -> str:
    return f"{collection(app)}{beneficiary.pk}/"


def test_create_with_arabic_digits_normalized():
    app = ApplicationFactory()
    response = client_for(app.doctor.user).post(
        collection(app),
        {
            "kinship": "WIFE",
            "full_name": " سارة   محمود علي ",
            "birth_year": "١٩٨٨",
            "national_id": "٢٨٨٠٣١٥٠١٠١٢٤٢",
        },
        format="json",
    )
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["row_number"] == 1
    assert body["full_name"] == "سارة محمود علي"
    assert body["birth_year"] == 1988
    assert body["national_id"] == "28803150101242"
    assert body["is_active"] is True
    assert {r["type"] for r in body["required_documents"]} == {
        "BENEFICIARY_NATIONAL_ID",
        "MARRIAGE_CERTIFICATE",
        "INSURANCE_PRINT",
    }
    assert body["documents"] == []
    assert "warnings" not in body  # cross-application duplicates are for admins only


def test_create_takes_the_lowest_free_row():
    app = ApplicationFactory()
    BeneficiaryFactory(application=app, row_number=1)
    BeneficiaryFactory(application=app, row_number=3)
    body = client_for(app.doctor.user).post(collection(app), {"kinship": "DAUGHTER"}).json()
    assert body["row_number"] == 2


def test_create_on_a_taken_row_is_refused():
    app = ApplicationFactory()
    BeneficiaryFactory(application=app, row_number=1)
    response = client_for(app.doctor.user).post(
        collection(app), {"row_number": 1, "kinship": "DAUGHTER"}
    )
    assert response.status_code == 400
    assert "row_number" in response.json()["error"]["fields"]


def test_row_limit_enforced(settings):
    settings.MAX_BENEFICIARIES = 2
    app = ApplicationFactory()
    client = client_for(app.doctor.user)
    for _ in range(2):
        assert client.post(collection(app), {"kinship": "DAUGHTER"}).status_code == 201
    response = client.post(collection(app), {"kinship": "DAUGHTER"})
    assert response.status_code == 400
    assert response.json()["error"]["fields"]["row_number"] == ["لا يمكن إضافة أكثر من 2 مستفيدين"]


def test_list_is_ordered_by_row():
    app = ApplicationFactory()
    BeneficiaryFactory(application=app, row_number=2, full_name="ب")
    BeneficiaryFactory(application=app, row_number=1, full_name="أ")
    body = client_for(app.doctor.user).get(collection(app)).json()
    assert [b["row_number"] for b in body] == [1, 2]


def test_patch_updates_only_given_fields():
    app = ApplicationFactory()
    b = BeneficiaryFactory(
        application=app, kinship=Kinship.DAUGHTER, full_name="مريم", birth_year=2018
    )
    response = client_for(app.doctor.user).patch(
        item(app, b), {"birth_year": "٢٠١٧"}, format="json"
    )
    assert response.status_code == 200
    b.refresh_from_db()
    assert (b.kinship, b.full_name, b.birth_year) == (Kinship.DAUGHTER, "مريم", 2017)


def test_kinship_change_removes_documents():
    app = ApplicationFactory()
    b = BeneficiaryFactory(application=app, kinship=Kinship.SON_MINOR)
    doc = DocumentFactory(
        application=app, beneficiary=b, document_type=DocumentType.BIRTH_CERTIFICATE
    )
    response = client_for(app.doctor.user).patch(item(app, b), {"kinship": "SON_UNIVERSITY"})
    assert response.status_code == 200
    assert response.json()["documents"] == []
    assert Document.all_objects.get(pk=doc.pk).deleted_at is not None


def test_same_kinship_keeps_documents():
    app = ApplicationFactory()
    b = BeneficiaryFactory(application=app, kinship=Kinship.SON_MINOR)
    DocumentFactory(application=app, beneficiary=b, document_type=DocumentType.BIRTH_CERTIFICATE)
    response = client_for(app.doctor.user).patch(item(app, b), {"full_name": "عمر أحمد"})
    assert len(response.json()["documents"]) == 1


def test_delete_removes_row_and_soft_deletes_documents():
    app = ApplicationFactory()
    b = BeneficiaryFactory(application=app)
    doc = DocumentFactory(
        application=app, beneficiary=b, document_type=DocumentType.BIRTH_CERTIFICATE
    )
    response = client_for(app.doctor.user).delete(item(app, b))
    assert response.status_code == 204
    assert not Beneficiary.objects.filter(pk=b.pk).exists()
    assert Document.all_objects.get(pk=doc.pk).deleted_at is not None


def test_duplicate_national_id_in_application_rejected():
    app = ApplicationFactory()
    BeneficiaryFactory(application=app, national_id="28803150101242", kinship=Kinship.WIFE)
    response = client_for(app.doctor.user).post(
        collection(app), {"kinship": "MOTHER", "national_id": "28803150101242"}
    )
    assert response.status_code == 400
    assert "national_id" in response.json()["error"]["fields"]


def test_member_national_id_rejected():
    app = ApplicationFactory()
    response = client_for(app.doctor.user).post(
        collection(app), {"kinship": "MOTHER", "national_id": app.doctor.national_id}
    )
    assert response.status_code == 400


def test_invalid_kinship_rejected():
    app = ApplicationFactory()
    response = client_for(app.doctor.user).post(collection(app), {"kinship": "BROTHER"})
    assert response.status_code == 400
    assert "kinship" in response.json()["error"]["fields"]


@pytest.mark.parametrize("status", [S.SUBMITTED, S.UNDER_REVIEW, S.APPROVED, S.REJECTED])
def test_not_editable_409(status):
    app = ApplicationFactory(status=status, reference_number="MED-2026-000001")
    b = BeneficiaryFactory(application=app)
    client = client_for(app.doctor.user)
    assert client.post(collection(app), {"kinship": "DAUGHTER"}).status_code == 409
    assert client.patch(item(app, b), {"full_name": "اسم"}).status_code == 409
    assert client.delete(item(app, b)).status_code == 409
    assert Beneficiary.objects.filter(pk=b.pk).exists()


def test_needs_correction_is_editable():
    app = ApplicationFactory(status=S.NEEDS_CORRECTION, reference_number="MED-2026-000001")
    assert (
        client_for(app.doctor.user).post(collection(app), {"kinship": "DAUGHTER"}).status_code
        == 201
    )


# --- IDOR ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["get_list", "post", "patch", "delete"])
def test_other_doctors_application_404(method):
    victim_app = ApplicationFactory()
    b = BeneficiaryFactory(application=victim_app, full_name="الأصل")
    client = client_for(DoctorFactory().user)
    response = {
        "get_list": lambda: client.get(collection(victim_app)),
        "post": lambda: client.post(collection(victim_app), {"kinship": "DAUGHTER"}),
        "patch": lambda: client.patch(item(victim_app, b), {"full_name": "مخترق"}),
        "delete": lambda: client.delete(item(victim_app, b)),
    }[method]()
    assert response.status_code == 404
    b.refresh_from_db()
    assert b.full_name == "الأصل"
    assert victim_app.beneficiaries.count() == 1


def test_beneficiary_of_another_application_through_own_application_404():
    """A valid own application id must not unlock someone else's beneficiary id."""
    own = ApplicationFactory()
    foreign = BeneficiaryFactory(application=ApplicationFactory(), full_name="الأصل")
    response = client_for(own.doctor.user).patch(item(own, foreign), {"full_name": "مخترق"})
    assert response.status_code == 404
    foreign.refresh_from_db()
    assert foreign.full_name == "الأصل"


def test_admin_gets_403():
    app = ApplicationFactory()
    assert client_for(AdminUserFactory()).get(collection(app)).status_code == 403
