"""Live smoke test of the doctor flow over real HTTP (session cookie + CSRF), against a running
development server with docker compose PostgreSQL + Azurite.

    docker compose up -d                       # repo root
    python manage.py migrate && python manage.py seed_dev_data
    python manage.py runserver 8000            # development settings
    python scripts/smoke_api.py --base http://127.0.0.1:8000 --email new.doctor@dev.local

dev login → profile → draft → beneficiary → upload documents (Azurite) → OCR (mock) → fee quote
→ validation → receipt + declaration → submit → reference number. Uses only the public API.
"""

import argparse
import io
import sys

import requests
from PIL import Image

PROFILE = {
    "full_name": "أحمد محمد علي حسن",
    "national_id": "٢٨٥٠٦١٥٠١٠١٢٣٤",
    "religion": "MUSLIM",
    "phone_number": "01012345678",
    "syndicate_type": "HUMAN_MEDICINE",
    "sub_syndicate": "القاهرة",
    "syndicate_registration_number": "12345",
    "syndicate_registration_year": "٢٠١٤",
    "governorate": "القاهرة",
    "neighborhood": "مدينة نصر",
    "address": "شارع عباس العقاد",
}


def png(size=(800, 600)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.session = requests.Session()

    def _headers(self) -> dict:
        return {"X-CSRFToken": self.session.cookies.get("csrftoken", ""), "Referer": self.base}

    def call(self, method: str, path: str, expected: int, **kwargs):
        response = self.session.request(
            method, f"{self.base}{path}", headers=self._headers(), timeout=30, **kwargs
        )
        if response.status_code != expected:
            sys.exit(f"FAILED {method} {path}: {response.status_code} {response.text[:500]}")
        return response.json() if response.content else None


def ok(message: str) -> None:
    print(f"  [ok] {message}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--email", default="new.doctor@dev.local")
    args = parser.parse_args()
    api = Api(args.base)

    api.call("GET", "/api/health/", 200)
    api.call("GET", "/api/ready/", 200)
    ok("health + readiness")
    api.call("GET", "/api/v1/auth/me/", 401)
    api.call("POST", "/api/v1/auth/dev/login/", 200, json={"email": args.email})
    me = api.call("GET", "/api/v1/auth/me/", 200)
    ok(f"dev login as {me['user']['email']} ({me['user']['role']})")

    application = api.call("POST", "/api/v1/applications/", 201)
    app = f"/api/v1/applications/{application['id']}/"
    ok(f"draft created {application['id']}")
    profile = api.call("PATCH", "/api/v1/profile/", 200, json=PROFILE)
    nid = profile["national_id"]
    ok(f"profile saved, national ID normalized to {nid[:2]}...{nid[-3:]}")
    api.call("PATCH", app, 200, json={"work_status": "WORKING"})

    wife = api.call("POST", f"{app}beneficiaries/", 201, json={
        "kinship": "WIFE", "full_name": "سارة محمود علي", "birth_year": 1988,
        "national_id": "28803150101242"})  # fmt: skip
    son = api.call(
        "POST",
        f"{app}beneficiaries/",
        201,
        json={"kinship": "SON_MINOR", "full_name": "عمر أحمد محمد", "birth_year": 2015},
    )
    ok("beneficiaries added (WIFE, SON_MINOR)")

    def upload(doc_type, beneficiary=None):
        data = {"document_type": doc_type}
        if beneficiary:
            data["beneficiary_id"] = beneficiary["id"]
        files = {"file": (f"{doc_type.lower()}.png", png(), "image/png")}
        return api.call("POST", f"{app}documents/", 201, data=data, files=files)

    front = upload("NATIONAL_ID_FRONT")
    upload("NATIONAL_ID_BACK")
    upload("SYNDICATE_ID")
    for doc_type in ("BENEFICIARY_NATIONAL_ID", "MARRIAGE_CERTIFICATE", "INSURANCE_PRINT"):
        upload(doc_type, wife)
    upload("BIRTH_CERTIFICATE", son)
    content = api.session.get(f"{args.base}{front['content_url']}", timeout=30)
    if content.status_code != 200 or content.content[:4] != b"\x89PNG":
        sys.exit(f"FAILED content stream: {content.status_code}")
    ok("7 documents uploaded to Azurite; content streamed back through the API")

    suggestion = api.call("POST", f"/api/v1/documents/{front['id']}/extract/", 200)
    ok(f"OCR suggestions: {sorted(suggestion['fields'])}")

    fees = api.call("GET", f"{app}fees/", 200)
    ok(f"fee quote: tier {fees['tier']}, total {fees['total']} EGP")
    validation = api.call("GET", f"{app}validation/", 200)
    steps, ready = validation["steps_complete"], validation["submit_ready"]
    ok(f"validation: steps {steps}, submit_ready={ready}")

    upload("PAYMENT_RECEIPT")
    api.call("PATCH", app, 200, json={"declaration_name": PROFILE["full_name"],
                                      "declaration_accepted": True})  # fmt: skip
    submitted = api.call("POST", f"{app}submit/", 200)
    ok(f"submitted: status {submitted['status']}, reference {submitted['reference_number']}, "
       f"fee snapshot {submitted['fee_snapshot']['total']} EGP")  # fmt: skip


if __name__ == "__main__":
    main()
