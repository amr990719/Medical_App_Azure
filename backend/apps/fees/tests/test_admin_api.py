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
    current = FeeSchedule.objects.get(fiscal_year=2026, is_active=True)
    payload = {
        "fiscal_year": 2026,
        "tier_fees": copy.deepcopy(current.tier_fees),
        "tier_boundaries": [5, 10, 15],
        "admin_fee_base": 200,
        "admin_fee_per_beneficiary": 175,
        "age_cap_threshold": 70,
        "age_cap_amount": 500,
        "registration_year_min": 1950,
    }
    payload.update(overrides)
    return payload


def test_list_and_detail_show_the_active_version_and_the_legacy_one():
    admin = client_for(AdminUserFactory())
    rows = [r for r in admin.get(URL).json()["results"] if r["fiscal_year"] == 2026]
    assert [(r["version"], r["is_active"]) for r in rows] == [(2, True), (1, False)]
    current = admin.get(f"{URL}{rows[0]['id']}/").json()
    assert current["tier_fees"]["3"]["spouse"] == 1100
    assert current["tier_fees"]["0"]["grad_son"] is None
    assert current["admin_fee_formula"] == "PER_BENEFICIARY"
    assert (current["admin_fee_base"], current["admin_fee_per_beneficiary"]) == (200, 175)
    assert current["admin_fee_member_only"] is None
    legacy = admin.get(f"{URL}{rows[1]['id']}/").json()
    assert sorted(legacy["tier_fees"]) == ["1", "2", "3", "4"]
    assert legacy["admin_fee_formula"] == "FLAT"
    assert (legacy["admin_fee_member_only"], legacy["admin_fee_with_beneficiaries"]) == (150, 175)
    assert (legacy["admin_fee_base"], legacy["admin_fee_per_beneficiary"]) == (None, None)


def test_new_fee_schedule_version_deactivates_previous_and_keeps_its_amounts():
    admin_user = AdminUserFactory()
    app = build_submittable_application()
    submit(app, actor=app.doctor.user)  # locks v2
    payload = fy2026_payload(admin_fee_base=250)
    payload["tier_fees"]["1"]["member"] = 650
    response = client_for(admin_user).post(URL, payload, format="json")
    assert response.status_code == 201, response.json()
    body = response.json()
    assert (body["version"], body["is_active"], body["locked_at"]) == (3, True, None)
    assert (body["admin_fee_formula"], body["admin_fee_base"]) == ("PER_BENEFICIARY", 250)
    assert body["tier_fees"]["0"]["grad_son"] is None
    v2 = FeeSchedule.objects.get(fiscal_year=2026, version=2)
    assert v2.is_active is False
    assert v2.is_locked is True
    assert (v2.tier_fees["1"]["member"], v2.admin_fee_base) == (660, 200)
    entry = AuditLog.objects.get(action=AuditAction.FEE_SCHEDULE_CHANGED)
    assert entry.user == admin_user
    assert entry.metadata["version"] == 3


def test_formula_and_legacy_amounts_are_not_writable():
    payload = fy2026_payload(
        admin_fee_formula="FLAT", admin_fee_member_only=1, admin_fee_with_beneficiaries=2
    )
    body = client_for(AdminUserFactory()).post(URL, payload, format="json").json()
    assert body["admin_fee_formula"] == "PER_BENEFICIARY"
    assert (body["admin_fee_member_only"], body["admin_fee_with_beneficiaries"]) == (None, None)


def test_new_version_drives_live_quotes_but_not_snapshots():
    admin = client_for(AdminUserFactory())
    submitted_app = build_submittable_application()
    submit(submitted_app, actor=submitted_app.doctor.user)
    draft = build_submittable_application(doctor=DoctorFactory())
    payload = fy2026_payload(admin_fee_per_beneficiary=100)
    payload["tier_fees"]["3"]["member"] = 900
    admin.post(URL, payload, format="json")
    doctor = client_for(draft.doctor.user)
    # tier 3: 900 + 1100 + 605 + 605 + (200 + 3 × 100)
    assert doctor.get(f"/api/v1/applications/{draft.pk}/fees/").json()["total"] == 3710
    owner = client_for(submitted_app.doctor.user)
    assert owner.get(f"/api/v1/applications/{submitted_app.pk}/fees/").json()["total"] == 3860


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p["tier_fees"]["1"].update(member=600.5),
        lambda p: p["tier_fees"]["1"].update(member="600"),
        lambda p: p["tier_fees"]["1"].pop("spouse"),
        lambda p: p["tier_fees"].pop("4"),
        lambda p: p["tier_fees"].pop("0"),  # new versions must define tier 0
        lambda p: p["tier_fees"]["1"].update(grad_son=None),
        lambda p: p["tier_fees"]["0"].update(member=None),
        lambda p: p.update(tier_boundaries=[10, 5, 15]),
        lambda p: p["tier_fees"]["2"].update(child=-1),
        lambda p: p.update(admin_fee_base=None),
        lambda p: p.pop("admin_fee_per_beneficiary"),
        lambda p: p.update(admin_fee_per_beneficiary=-5),
    ],
    ids=["float", "string", "missing-key", "missing-tier", "missing-tier-0", "null-tier-1",
         "null-member", "boundaries", "negative", "null-admin-base", "missing-per-beneficiary",
         "negative-per-beneficiary"],
)  # fmt: skip
def test_invalid_schedule_rejected(mutate):
    payload = fy2026_payload()
    mutate(payload)
    response = client_for(AdminUserFactory()).post(URL, payload, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert FeeSchedule.objects.filter(fiscal_year=2026).count() == 2


def test_tier_0_grad_son_may_be_an_amount():
    payload = fy2026_payload()
    payload["tier_fees"]["0"]["grad_son"] = 1100
    response = client_for(AdminUserFactory()).post(URL, payload, format="json")
    assert response.status_code == 201
    assert response.json()["tier_fees"]["0"]["grad_son"] == 1100


def test_new_fiscal_year_starts_at_version_1():
    response = client_for(AdminUserFactory()).post(
        URL, fy2026_payload(fiscal_year=2027), format="json"
    )
    assert response.status_code == 201
    assert response.json()["version"] == 1


def test_doctor_cannot_create_schedules():
    response = client_for(DoctorFactory().user).post(URL, fy2026_payload(), format="json")
    assert response.status_code == 403
