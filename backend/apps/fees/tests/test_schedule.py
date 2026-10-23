import importlib

import pytest
from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.fees.factories import FY2026_TIER_FEES, FY2026_V1_TIER_FEES, FeeScheduleFactory
from apps.fees.models import (
    AdminFeeFormula,
    FeeSchedule,
    FeeScheduleLocked,
    validate_tier_fees,
)
from apps.fees.services import NoActiveFeeSchedule, active_schedule

pytestmark = pytest.mark.django_db


def test_fy2026_v1_seed_is_kept_but_inactive():
    schedule = FeeSchedule.objects.get(fiscal_year=2026, version=1)
    assert schedule.is_active is False
    assert schedule.tier_fees == FY2026_V1_TIER_FEES
    assert schedule.admin_fee_formula == AdminFeeFormula.FLAT
    assert (schedule.admin_fee_member_only, schedule.admin_fee_with_beneficiaries) == (150, 175)
    assert (schedule.admin_fee_base, schedule.admin_fee_per_beneficiary) == (None, None)


def test_fresh_install_activates_fy2026_v2():
    schedule = FeeSchedule.objects.get(fiscal_year=2026, is_active=True)
    assert schedule.version == 2
    assert schedule.tier_fees == FY2026_TIER_FEES
    assert schedule.tier_fees["0"]["grad_son"] is None
    assert schedule.tier_fees["3"]["spouse"] == 1100
    assert schedule.admin_fee_formula == AdminFeeFormula.PER_BENEFICIARY
    assert (schedule.admin_fee_base, schedule.admin_fee_per_beneficiary) == (200, 175)
    assert (schedule.admin_fee_member_only, schedule.admin_fee_with_beneficiaries) == (None, None)
    assert schedule.age_cap_threshold == 70
    assert schedule.age_cap_amount == 500
    assert schedule.registration_year_min == 1950
    assert schedule.tier_boundaries == [5, 10, 15]
    assert schedule.locked_at is None


def test_active_schedule_returns_version_2():
    assert active_schedule(2026).version == 2


def test_active_schedule_missing_raises():
    with pytest.raises(NoActiveFeeSchedule):
        active_schedule(2031)


def test_only_one_active_schedule_per_fiscal_year():
    with pytest.raises(IntegrityError):
        FeeScheduleFactory(fiscal_year=2026, version=3, is_active=True)


def test_inactive_new_version_is_allowed():
    FeeScheduleFactory(fiscal_year=2026, version=3, is_active=False)
    assert FeeSchedule.objects.filter(fiscal_year=2026).count() == 3


def test_version_is_unique_per_fiscal_year():
    with pytest.raises(IntegrityError):
        FeeScheduleFactory(fiscal_year=2026, version=1, is_active=False)


def test_negative_amounts_are_rejected_by_the_database():
    with pytest.raises(IntegrityError), transaction.atomic():
        FeeSchedule.objects.filter(fiscal_year=2026).update(age_cap_amount=-1)


def test_malformed_tier_fees_are_rejected():
    with pytest.raises(ValidationError):
        FeeScheduleFactory(fiscal_year=2027, tier_fees={"1": {"member": 600}})
    with pytest.raises(ValidationError):
        bad = {k: {**v, "spouse": 12.5} for k, v in FY2026_TIER_FEES.items()}
        FeeScheduleFactory(fiscal_year=2027, tier_fees=bad)


def _locked_active():
    schedule = active_schedule(2026)
    FeeSchedule.objects.filter(pk=schedule.pk).update(locked_at=timezone.now())
    schedule.refresh_from_db()
    return schedule


def test_locked_schedule_cannot_change_amounts():
    schedule = _locked_active()
    assert schedule.is_locked is True
    schedule.admin_fee_base = 1
    with pytest.raises(FeeScheduleLocked):
        schedule.save()


@pytest.mark.parametrize(
    ("field", "value"),
    [("admin_fee_per_beneficiary", 1), ("age_cap_amount", 400), ("tier_boundaries", [4, 9, 14])],
)
def test_locked_schedule_protects_fee_and_admin_fee_settings(field, value):
    schedule = _locked_active()
    setattr(schedule, field, value)
    with pytest.raises(FeeScheduleLocked):
        schedule.save()


def test_locked_schedule_cannot_switch_formula_or_tier_fees():
    schedule = _locked_active()
    schedule.tier_fees = {tier: dict(row) for tier, row in FY2026_TIER_FEES.items()}
    schedule.tier_fees["0"]["member"] = 1
    with pytest.raises(FeeScheduleLocked):
        schedule.save()
    schedule.refresh_from_db()
    schedule.admin_fee_formula = AdminFeeFormula.FLAT
    with pytest.raises((FeeScheduleLocked, ValidationError)):
        schedule.save()


def test_locked_schedule_can_still_be_deactivated():
    schedule = _locked_active()
    schedule.is_active = False
    schedule.save()
    assert FeeSchedule.objects.get(pk=schedule.pk).is_active is False


def test_locked_legacy_schedule_can_still_be_deactivated_under_the_new_validation():
    FeeSchedule.objects.filter(fiscal_year=2026, version=2).update(is_active=False)
    FeeSchedule.objects.filter(fiscal_year=2026, version=1).update(
        locked_at=timezone.now(), is_active=True
    )
    legacy = FeeSchedule.objects.get(fiscal_year=2026, version=1)
    legacy.is_active = False
    legacy.save(update_fields=["is_active"])
    assert FeeSchedule.objects.get(pk=legacy.pk).is_active is False


def test_locked_schedule_cannot_be_deleted():
    schedule = _locked_active()
    with pytest.raises(FeeScheduleLocked):
        schedule.delete()


# --- tier_fees validation ---------------------------------------------------------------------


def _fees(tier: str, key: str, value) -> dict:
    fees = {t: dict(row) for t, row in FY2026_TIER_FEES.items()}
    fees[tier][key] = value
    return fees


def test_null_is_allowed_only_for_tier_0_grad_son():
    validate_tier_fees(FY2026_TIER_FEES)
    validate_tier_fees(_fees("0", "grad_son", 1100))  # an amount is fine too
    for tier, key in (("0", "member"), ("0", "child"), ("1", "grad_son"), ("4", "parent")):
        with pytest.raises(ValidationError):
            validate_tier_fees(_fees(tier, key, None))


@pytest.mark.parametrize("bad", [-1, 12.5, "400", True])
def test_amounts_stay_non_negative_integers(bad):
    with pytest.raises(ValidationError):
        validate_tier_fees(_fees("0", "member", bad))
    with pytest.raises(ValidationError):
        validate_tier_fees(_fees("0", "grad_son", bad))


def test_legacy_four_tier_schedules_remain_valid_and_partial_sets_do_not():
    validate_tier_fees(FY2026_V1_TIER_FEES)
    with pytest.raises(ValidationError):
        validate_tier_fees({k: v for k, v in FY2026_TIER_FEES.items() if k != "3"})
    with pytest.raises(ValidationError):  # a null grad_son is not allowed outside tier 0
        validate_tier_fees({**FY2026_V1_TIER_FEES, "1": FY2026_TIER_FEES["0"]})


@pytest.mark.parametrize(
    "fields",
    [
        {"admin_fee_formula": AdminFeeFormula.PER_BENEFICIARY, "admin_fee_base": None},
        {"admin_fee_formula": AdminFeeFormula.FLAT, "admin_fee_member_only": None,
         "admin_fee_with_beneficiaries": 175},
    ],
)  # fmt: skip
def test_admin_fee_formula_needs_its_amounts(fields):
    with pytest.raises(ValidationError):
        FeeScheduleFactory(fiscal_year=2027, **fields)


def test_database_requires_the_formula_amounts():
    with pytest.raises(IntegrityError), transaction.atomic():
        FeeSchedule.objects.filter(fiscal_year=2026, version=2).update(admin_fee_base=None)
    with pytest.raises(IntegrityError), transaction.atomic():
        FeeSchedule.objects.filter(fiscal_year=2026, version=1).update(admin_fee_member_only=None)


# --- data migration 0004 (upgrade path; the fresh path is the test database itself) -----------

MIGRATION = importlib.import_module("apps.fees.migrations.0004_fy2026_v2_schedule")


def _as_before_upgrade() -> FeeSchedule:
    """The database as it was before 0004: version 1 active and used, no version 2."""
    FeeSchedule.objects.filter(fiscal_year=2026, version=2).delete()
    FeeSchedule.objects.filter(fiscal_year=2026, version=1).update(
        is_active=True, locked_at=timezone.now()
    )
    return FeeSchedule.objects.get(fiscal_year=2026, version=1)


def test_upgrade_activates_v2_and_keeps_v1_and_its_snapshots_intact():
    from apps.applications.factories import ApplicationFactory

    v1 = _as_before_upgrade()
    snapshot = {"fiscal_year": 2026, "tier": 3, "breakdown": [], "admin_fee": 175, "total": 3025}
    app = ApplicationFactory(fee_snapshot=snapshot, fee_schedule=v1)
    before = FeeSchedule.objects.filter(pk=v1.pk).values().get()

    MIGRATION.forwards(django_apps, None)

    after = FeeSchedule.objects.filter(pk=v1.pk).values().get()
    assert after == {**before, "is_active": False}  # only the flag changed, lock kept
    active = active_schedule(2026)
    assert (active.version, active.tier_fees) == (2, FY2026_TIER_FEES)
    app.refresh_from_db()
    assert (app.fee_snapshot, app.fee_schedule_id) == (snapshot, v1.pk)


def test_upgrade_is_idempotent():
    MIGRATION.forwards(django_apps, None)
    MIGRATION.forwards(django_apps, None)
    assert FeeSchedule.objects.filter(fiscal_year=2026).count() == 2
    assert active_schedule(2026).version == 2


def test_upgrade_after_an_admin_created_version_takes_the_next_number():
    FeeSchedule.objects.filter(fiscal_year=2026, version=2).delete()
    FeeScheduleFactory(fiscal_year=2026, version=3, is_active=True, admin_fee_base=250)
    MIGRATION.forwards(django_apps, None)
    assert active_schedule(2026).version == 4
    assert FeeSchedule.objects.get(fiscal_year=2026, version=3).is_active is False


def test_reverse_restores_v1_unless_v2_was_used():
    MIGRATION.backwards(django_apps, None)
    assert active_schedule(2026).version == 1
    MIGRATION.forwards(django_apps, None)
    FeeSchedule.objects.filter(fiscal_year=2026, version=2).update(locked_at=timezone.now())
    with pytest.raises(RuntimeError):
        MIGRATION.backwards(django_apps, None)
