"""Fee schedule administration (PROMPT.md §17.1, §44): view versions, create a new version."""

import copy

import pytest
from rest_framework.test import APIClient

from apps.accounts.factories import AdminUserFactory
from apps.applications.factories import build_submittable_application
from apps.applications.services import submit
from apps.audit.models import AuditAction, AuditLog
from apps.doctors.factories import DoctorFactory
from apps.fees.models import FeeSchedule

pytestmark = pytest.mark.django_db
URL = "/api/v1/admin/fee-schedules/"


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def fy2026_payload(**overrides) -> dict:
    current = FeeSchedule.objects.get(fiscal_year=2026, version=1)
    payload = {
        "fiscal_year": 2026,
        "tier_fees": copy.deepcopy(current.tier_fees),
        "tier_boundaries": [5, 10, 15],
        "admin_fee_member_only": 150,
        "admin_fee_with_beneficiaries": 175,
        "age_cap_threshold": 70,
        "age_cap_amount": 500,
        "registration_year_min": 1950,
    }
    payload.update(overrides)
    return payload


def test_list_and_detail():
    admin = client_for(AdminUserFactory())
    rows = admin.get(URL).json()["results"]
    seeded = next(r for r in rows if r["fiscal_year"] == 2026)
    assert seeded["version"] == 1
    assert seeded["is_active"] is True
    detail = admin.get(f"{URL}{seeded['id']}/").json()
    assert detail["tier_fees"]["3"]["spouse"] == 1000


def test_new_fee_schedule_version_deactivates_previous_and_keeps_its_amounts():
    admin_user = AdminUserFactory()
    app = build_submittable_application()
    submit(app, actor=app.doctor.user)  # locks v1
    payload = fy2026_payload()
    payload["tier_fees"]["1"]["member"] = 650
    response = client_for(admin_user).post(URL, payload, format="json")
    assert response.status_code == 201, response.json()
    body = response.json()
    assert (body["version"], body["is_active"], body["locked_at"]) == (2, True, None)
    v1 = FeeSchedule.objects.get(fiscal_year=2026, version=1)
    assert v1.is_active is False
    assert v1.is_locked is True
    assert v1.tier_fees["1"]["member"] == 600
    entry = AuditLog.objects.get(action=AuditAction.FEE_SCHEDULE_CHANGED)
    assert entry.user == admin_user
    assert entry.metadata["version"] == 2


def test_new_version_drives_live_quotes_but_not_snapshots():
    admin = client_for(AdminUserFactory())
    submitted_app = build_submittable_application()
    submit(submitted_app, actor=submitted_app.doctor.user)
    draft = build_submittable_application(doctor=DoctorFactory())
    payload = fy2026_payload()
    payload["tier_fees"]["3"]["member"] = 800
    admin.post(URL, payload, format="json")
    doctor = client_for(draft.doctor.user)
    assert doctor.get(f"/api/v1/applications/{draft.pk}/fees/").json()["total"] == 3075
    owner = client_for(submitted_app.doctor.user)
    assert owner.get(f"/api/v1/applications/{submitted_app.pk}/fees/").json()["total"] == 3025


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p["tier_fees"]["1"].update(member=600.5),
        lambda p: p["tier_fees"]["1"].update(member="600"),
        lambda p: p["tier_fees"]["1"].pop("spouse"),
        lambda p: p["tier_fees"].pop("4"),
        lambda p: p.update(tier_boundaries=[10, 5, 15]),
        lambda p: p["tier_fees"]["2"].update(child=-1),
    ],
    ids=["float", "string", "missing-key", "missing-tier", "boundaries", "negative"],
)
def test_invalid_schedule_rejected(mutate):
    payload = fy2026_payload()
    mutate(payload)
    response = client_for(AdminUserFactory()).post(URL, payload, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert FeeSchedule.objects.filter(fiscal_year=2026).count() == 1


def test_new_fiscal_year_starts_at_version_1():
    response = client_for(AdminUserFactory()).post(
        URL, fy2026_payload(fiscal_year=2027), format="json"
    )
    assert response.status_code == 201
    assert response.json()["version"] == 1


def test_doctor_cannot_create_schedules():
    response = client_for(DoctorFactory().user).post(URL, fy2026_payload(), format="json")
    assert response.status_code == 403
