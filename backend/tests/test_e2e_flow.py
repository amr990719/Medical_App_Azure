"""End-to-end API flow against PostgreSQL + the docker compose Azurite, the way the SPA drives it:
CSRF bootstrap → dev login (session cookie) → profile → draft → beneficiary → uploads to Azurite
→ OCR (mock) → fee quote → validation → declaration → submit → reference number.

Run with `-s` to see the trace: `pytest tests/test_e2e_flow.py -s`.
"""

import re

import pytest
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory
from apps.documents.models import Document
from apps.documents.storage import get_storage
from tests.files import png_upload

pytestmark = [pytest.mark.django_db, pytest.mark.azurite]

PROFILE = {
    "full_name": "أحمد محمد علي حسن",
    "national_id": "٢٨٥٠٦١٥٠١٠١٢٣٤",  # Eastern Arabic digits, normalized by the server
    "religion": "MUSLIM",
    "phone_number": "٠١٠١٢٣٤٥٦٧٨",
    "syndicate_type": "HUMAN_MEDICINE",
    "sub_syndicate": "القاهرة",
    "syndicate_registration_number": "12345",
    "syndicate_registration_year": "٢٠١٤",
    "governorate": "القاهرة",
    "neighborhood": "مدينة نصر",
    "address": "شارع عباس العقاد",
}


class Browser:
    """APIClient that behaves like the SPA: CSRF enforced, token from the csrftoken cookie."""

    def __init__(self) -> None:
        self.client = APIClient(enforce_csrf_checks=True)

    def _csrf(self) -> dict:
        return {"HTTP_X_CSRFTOKEN": self.client.cookies["csrftoken"].value}

    def get(self, url, **params):
        return self.client.get(url, params or None)

    def post(self, url, data=None, fmt="json"):
        return self.client.post(url, data or {}, format=fmt, **self._csrf())

    def patch(self, url, data):
        return self.client.patch(url, data, format="json", **self._csrf())


def step(title: str, detail: str = "") -> None:
    print(f"  [ok] {title}{' - ' + detail if detail else ''}")


def test_dev_login_to_reference_number_through_azurite(azurite_settings, settings):
    settings.OCR_ENABLED = True
    UserFactory(email="e2e.doctor@dev.local")
    browser = Browser()
    print()

    response = browser.get("/api/v1/auth/me/")
    assert response.status_code == 401 and "csrftoken" in response.cookies
    step("GET /auth/me/ (anonymous)", "401 + csrftoken cookie")

    response = browser.post("/api/v1/auth/dev/login/", {"email": "e2e.doctor@dev.local"})
    assert response.status_code == 200, response.json()
    assert browser.get("/api/v1/auth/me/").json()["user"]["role"] == "DOCTOR"
    step("POST /auth/dev/login/", "session cookie set, role DOCTOR")

    response = browser.patch("/api/v1/profile/", PROFILE)
    assert response.status_code == 200, response.json()
    profile = response.json()
    assert (profile["national_id"], profile["birth_year"], profile["gender"]) == (
        "28506150101234",
        1985,
        "MALE",
    )
    step("PATCH /profile/", "Arabic digits normalized, birth year + gender derived from ID")

    response = browser.post("/api/v1/applications/")
    assert response.status_code == 201
    app_id = response.json()["id"]
    base = f"/api/v1/applications/{app_id}/"
    step("POST /applications/", f"draft {app_id}")

    response = browser.patch(base, {"work_status": "WORKING"})
    assert response.status_code == 200

    beneficiaries = [
        {"kinship": "WIFE", "full_name": "سارة محمود علي", "birth_year": "١٩٨٨",
         "national_id": "28803150101242"},
        {"kinship": "SON_MINOR", "full_name": "عمر أحمد محمد", "birth_year": 2015},
        {"kinship": "DAUGHTER", "full_name": "مريم أحمد محمد", "birth_year": 2018},
    ]  # fmt: skip
    rows = []
    for data in beneficiaries:
        response = browser.post(f"{base}beneficiaries/", data)
        assert response.status_code == 201, response.json()
        rows.append(response.json())
    step("POST /beneficiaries/ x3", "WIFE 1988, SON_MINOR 2015, DAUGHTER 2018")

    def upload(doc_type, beneficiary_id=None):
        data = {"file": png_upload((800, 600), name=f"{doc_type.lower()}.png"),
                "document_type": doc_type}  # fmt: skip
        if beneficiary_id:
            data["beneficiary_id"] = beneficiary_id
        response = browser.post(f"{base}documents/", data, fmt="multipart")
        assert response.status_code == 201, response.json()
        return response.json()

    front = upload("NATIONAL_ID_FRONT")
    for doc_type in ("NATIONAL_ID_BACK", "SYNDICATE_ID"):
        upload(doc_type)
    wife, son, daughter = rows
    for doc_type in ("BENEFICIARY_NATIONAL_ID", "MARRIAGE_CERTIFICATE", "INSURANCE_PRINT"):
        upload(doc_type, wife["id"])
    for child in (son, daughter):
        upload("BIRTH_CERTIFICATE", child["id"])
    blob_name = Document.objects.get(pk=front["id"]).blob_name
    storage = get_storage()
    assert storage.exists(blob_name)
    assert storage.download(blob_name)[:4] == b"\x89PNG"
    assert re.fullmatch(
        rf"applications/{app_id}/doctor/national-id-front-[0-9a-f-]{{36}}\.png", blob_name
    )
    step("POST /documents/ x8", f"stored in Azurite container {settings.BLOB_CONTAINER}")

    response = browser.get(f"/api/v1/documents/{front['id']}/content/")
    assert response.status_code == 200 and response.content[:4] == b"\x89PNG"
    step("GET /documents/{id}/content/", "authorized stream from Azurite")

    response = browser.post(f"/api/v1/documents/{front['id']}/extract/")
    assert response.status_code == 200
    assert response.json()["fields"]["national_id"] == "28506150101234"
    step("POST /documents/{id}/extract/", "mock OCR suggestions (nothing saved)")

    fees = browser.get(f"{base}fees/").json()
    assert (fees["tier"], fees["total"]) == (3, 3025)
    step("GET /fees/", f"tier {fees['tier']}, total {fees['total']} EGP (worked example 2)")

    validation = browser.get(f"{base}validation/").json()
    assert [e["field"] for e in validation["errors"]] == ["declaration.name"]
    assert validation["submit_ready"] is False
    assert validation["steps_complete"] == {"1": True, "2": True, "3": True, "4": False, "5": False}
    step("GET /validation/", "steps 1-3 complete; declaration name + receipt still missing")

    response = browser.post(f"{base}submit/")
    assert response.status_code == 400
    missing = {e["field"] for e in response.json()["error"]["errors"]}
    assert missing == {"receipt", "declaration.name", "declaration.accepted"}
    step("POST /submit/ (early)", "400 VALIDATION_ERROR: receipt, declaration")

    upload("PAYMENT_RECEIPT")
    assert browser.get(base).json()["payment_status"] == "PENDING_REVIEW"
    response = browser.patch(
        base, {"declaration_name": "احمد محمد علي حسن", "declaration_accepted": True}
    )
    assert response.status_code == 200
    assert browser.get(f"{base}validation/").json()["submit_ready"] is True
    step("receipt + declaration", "payment PENDING_REVIEW, submit-ready")

    response = browser.post(f"{base}submit/")
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["status"] == "SUBMITTED"
    assert re.fullmatch(r"MED-2026-\d{6}", body["reference_number"])
    assert body["fee_snapshot"]["total"] == 3025
    step("POST /submit/", f"SUBMITTED, reference number {body['reference_number']}")
