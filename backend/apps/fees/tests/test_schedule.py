import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.fees.factories import FY2026_TIER_FEES, FeeScheduleFactory
from apps.fees.models import FeeSchedule, FeeScheduleLocked
from apps.fees.services import NoActiveFeeSchedule, active_schedule

pytestmark = pytest.mark.django_db


def test_fy2026_seed_exists():
    schedule = FeeSchedule.objects.get(fiscal_year=2026, version=1)
    assert schedule.is_active is True
    assert schedule.tier_fees == FY2026_TIER_FEES
    assert schedule.tier_fees["3"]["spouse"] == 1000
    assert schedule.admin_fee_member_only == 150
    assert schedule.admin_fee_with_beneficiaries == 175
    assert schedule.age_cap_threshold == 70
    assert schedule.age_cap_amount == 500
    assert schedule.registration_year_min == 1950
    assert schedule.tier_boundaries == [5, 10, 15]
    assert schedule.locked_at is None


def test_active_schedule_returns_the_seed():
    assert active_schedule(2026).version == 1


def test_active_schedule_missing_raises():
    with pytest.raises(NoActiveFeeSchedule):
        active_schedule(2031)


def test_only_one_active_schedule_per_fiscal_year():
    with pytest.raises(IntegrityError):
        FeeScheduleFactory(fiscal_year=2026, version=2, is_active=True)


def test_inactive_new_version_is_allowed():
    FeeScheduleFactory(fiscal_year=2026, version=2, is_active=False)
    assert FeeSchedule.objects.filter(fiscal_year=2026).count() == 2


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


def test_locked_schedule_cannot_change_amounts():
    schedule = active_schedule(2026)
    FeeSchedule.objects.filter(pk=schedule.pk).update(locked_at=timezone.now())
    schedule.refresh_from_db()
    assert schedule.is_locked is True
    schedule.admin_fee_member_only = 1
    with pytest.raises(FeeScheduleLocked):
        schedule.save()


def test_locked_schedule_can_still_be_deactivated():
    schedule = active_schedule(2026)
    FeeSchedule.objects.filter(pk=schedule.pk).update(locked_at=timezone.now())
    schedule.refresh_from_db()
    schedule.is_active = False
    schedule.save()
    assert FeeSchedule.objects.get(pk=schedule.pk).is_active is False


def test_locked_schedule_cannot_be_deleted():
    schedule = active_schedule(2026)
    FeeSchedule.objects.filter(pk=schedule.pk).update(locked_at=timezone.now())
    schedule.refresh_from_db()
    with pytest.raises(FeeScheduleLocked):
        schedule.delete()
