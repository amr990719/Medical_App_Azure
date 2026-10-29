import importlib

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.fees.factories import FY2026_TIER_FEES, FeeScheduleFactory
from apps.fees.models import FeeSchedule, FeeScheduleLocked, validate_tier_fees
from apps.fees.services import NoActiveFeeSchedule, active_schedule

pytestmark = pytest.mark.django_db

# FY 2026 version 1 exactly as fees.0002 seeded it (four tiers, FLAT 150 / 175).
SEED_0002 = importlib.import_module("apps.fees.migrations.0002_seed_fy2026")
FY2026_V1 = SEED_0002.FY2026
V3_0008 = importlib.import_module("apps.fees.migrations.0008_fy2026_v3_schedule")


def test_fresh_install_has_fy2026_v3_only_and_active():
    assert not FeeSchedule.objects.filter(fiscal_year=2026, version__in=[1, 2]).exists()
    schedule = FeeSchedule.objects.get(fiscal_year=2026)
    assert (schedule.version, schedule.is_active) == (3, True)
    assert schedule.tier_fees == FY2026_TIER_FEES
    assert schedule.tier_fees["0"]["grad_son"] is None
    assert schedule.tier_fees["3"]["spouse"] == 1100
    assert (schedule.admin_fee_base, schedule.admin_fee_per_beneficiary) == (200, 175)
    assert schedule.service_fee == 800
    assert schedule.age_cap_threshold == 70
    assert schedule.age_cap_amount == 500
    assert schedule.registration_year_min == 1950
    assert schedule.tier_boundaries == [5, 10, 15]
    assert schedule.locked_at is None


def test_legacy_administrative_fee_fields_are_gone():
    removed = {"admin_fee_formula", "admin_fee_member_only", "admin_fee_with_beneficiaries"}
    assert removed.isdisjoint(f.name for f in FeeSchedule._meta.get_fields())


def test_active_schedule_returns_version_3():
    assert active_schedule(2026).version == 3


def test_active_schedule_missing_raises():
    with pytest.raises(NoActiveFeeSchedule):
        active_schedule(2031)


def test_only_one_active_schedule_per_fiscal_year():
    with pytest.raises(IntegrityError):
        FeeScheduleFactory(fiscal_year=2026, version=4, is_active=True)


def test_inactive_new_version_is_allowed():
    FeeScheduleFactory(fiscal_year=2026, version=4, is_active=False)
    assert FeeSchedule.objects.filter(fiscal_year=2026).count() == 2


def test_version_is_unique_per_fiscal_year():
    with pytest.raises(IntegrityError):
        FeeScheduleFactory(fiscal_year=2026, version=3, is_active=False)


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
    [
        ("admin_fee_per_beneficiary", 1),
        ("service_fee", 900),
        ("age_cap_amount", 400),
        ("tier_boundaries", [4, 9, 14]),
    ],
)
def test_locked_schedule_protects_fee_and_admin_fee_settings(field, value):
    schedule = _locked_active()
    setattr(schedule, field, value)
    with pytest.raises(FeeScheduleLocked):
        schedule.save()


def test_locked_schedule_cannot_change_tier_fees():
    schedule = _locked_active()
    schedule.tier_fees = {tier: dict(row) for tier, row in FY2026_TIER_FEES.items()}
    schedule.tier_fees["0"]["member"] = 1
    with pytest.raises(FeeScheduleLocked):
        schedule.save()


def test_locked_schedule_can_still_be_deactivated():
    schedule = _locked_active()
    schedule.is_active = False
    schedule.save()
    assert FeeSchedule.objects.get(pk=schedule.pk).is_active is False


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


def test_every_schedule_must_define_tiers_0_to_4():
    with pytest.raises(ValidationError):  # the old four-tier shape is no longer accepted
        validate_tier_fees(FY2026_V1["tier_fees"])
    with pytest.raises(ValidationError):
        validate_tier_fees({k: v for k, v in FY2026_TIER_FEES.items() if k != "3"})
    with pytest.raises(ValidationError):
        validate_tier_fees({**FY2026_TIER_FEES, "5": FY2026_TIER_FEES["4"]})
    with pytest.raises(ValidationError):
        FeeScheduleFactory(fiscal_year=2027, tier_fees=FY2026_V1["tier_fees"])


@pytest.mark.parametrize("field", ["admin_fee_base", "admin_fee_per_beneficiary", "service_fee"])
def test_administrative_and_service_fee_amounts_are_required(field):
    with pytest.raises(ValidationError):
        FeeScheduleFactory(fiscal_year=2027, **{field: None})
    with pytest.raises(IntegrityError), transaction.atomic():
        FeeSchedule.objects.filter(fiscal_year=2026).update(**{field: None})


# --- migrations 0005/0006 against a real schema (existing-database upgrade path) --------------
# The fresh path is the test database itself (tests above). These roll `fees` back, rebuild the
# old data with the HISTORICAL models, and migrate forward exactly as `migrate` does.

LEAF_0002 = ("fees", "0002_seed_fy2026")
LEAF_0004 = ("fees", "0004_fy2026_v2_schedule")
LEAF_0006 = ("fees", "0006_remove_legacy_admin_fee")
LEAF_0007 = ("fees", "0007_feeschedule_service_fee")


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.migrate([target] if target else executor.loader.graph.leaf_nodes())
    return executor.loader.project_state([target]).apps if target else None


@pytest.fixture
def migrate_back():
    """Roll `fees` back to a migration; always migrate forward again afterwards.

    The test database was migrated to the latest state, where 0008 replaced version 2 by
    version 3 with the same tier amounts. Rolling back keeps that row, so it is numbered 2
    again: the database then looks as it did before 0008 (FY 2026 v2 only)."""

    def migrate(target):
        old = _migrate(target)
        old.get_model("fees", "FeeSchedule").objects.filter(fiscal_year=2026).update(version=2)
        return old

    yield migrate
    _migrate(None)


def _application(**fields):
    from apps.applications.factories import ApplicationFactory
    from apps.beneficiaries.factories import BeneficiaryFactory
    from apps.documents.factories import DocumentFactory
    from apps.reference.constants import ApplicationStatus

    defaults = {
        "status": ApplicationStatus.SUBMITTED,
        "reference_number": "MED-2026-000777",
        "submitted_at": timezone.now(),
    }
    app = ApplicationFactory(
        **{**defaults, **fields},
        fee_snapshot={
            "fiscal_year": 2026, "tier": 3, "admin_fee": 175, "total": 1925,
            "breakdown": [{"label": "العضو الأصلي", "fee": 750, "note": ""},
                          {"label": "سارة", "fee": 1000, "note": ""},
                          {"label": "رسوم إدارية", "fee": 175, "note": ""}],
            "is_valid": True, "error_message": "", "schedule_id": "",
        },
        submitted_snapshot={"beneficiaries": [{"row_number": 1, "full_name": "سارة"}]},
    )  # fmt: skip
    BeneficiaryFactory(application=app, row_number=1, full_name="سارة")
    DocumentFactory(application=app)
    return app


def _fingerprint():
    from apps.applications.models import InsuranceApplication
    from apps.audit.models import AuditLog
    from apps.beneficiaries.models import Beneficiary
    from apps.documents.models import Document

    return {
        "applications": list(InsuranceApplication.objects.order_by("pk").values()),
        "beneficiaries": list(Beneficiary.objects.order_by("pk").values()),
        "documents": list(Document.objects.order_by("pk").values()),
        "audit": list(AuditLog.objects.order_by("pk").values()),
    }


def _without_schedule_ref(fingerprint):
    for row in fingerprint["applications"]:
        row["fee_schedule_id"] = None
    return fingerprint


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_upgrade_from_v1_removes_it_and_keeps_every_record(migrate_back):
    """The dev database path: fees at 0002, v1 active, locked and used by a submission."""
    from apps.applications.models import InsuranceApplication
    from apps.audit.models import AuditAction
    from apps.audit.services import record

    app = _application()
    draft = _application(reference_number=None, status="DRAFT", submitted_at=None)
    old = migrate_back(LEAF_0002)
    SEED_0002.seed(old, None)  # version 1 as originally seeded: active
    v1 = old.get_model("fees", "FeeSchedule").objects.get(fiscal_year=2026, version=1)
    old.get_model("fees", "FeeSchedule").objects.filter(pk=v1.pk).update(locked_at=timezone.now())
    snapshot = {**app.fee_snapshot, "schedule_id": str(v1.pk)}
    used = InsuranceApplication.objects.filter(pk=app.pk)
    used.update(fee_schedule_id=v1.pk, fee_snapshot=snapshot)
    record(
        actor=app.doctor.user, action=AuditAction.FEE_SNAPSHOT_CREATED, obj=app,
        metadata={"schedule_id": str(v1.pk), "tier": 3, "total": 1925},
    )  # fmt: skip
    before = _fingerprint()

    new = _migrate(LEAF_0006)

    NewFeeSchedule = new.get_model("fees", "FeeSchedule")
    assert not NewFeeSchedule.objects.filter(pk=v1.pk).exists()
    assert not NewFeeSchedule.objects.filter(fiscal_year=2026, version=1).exists()
    v2 = NewFeeSchedule.objects.get(fiscal_year=2026)
    assert (v2.version, v2.is_active, v2.tier_fees) == (2, True, FY2026_TIER_FEES)
    assert (v2.admin_fee_base, v2.admin_fee_per_beneficiary) == (200, 175)
    # Every row identical except the cleared reference — snapshots byte-for-byte, updated_at too.
    assert _fingerprint() == _without_schedule_ref(before)
    app.refresh_from_db()
    assert (app.fee_schedule_id, app.fee_snapshot) == (None, snapshot)
    assert app.fee_snapshot["schedule_id"] == str(v1.pk)  # history, not a live reference
    draft.refresh_from_db()
    assert draft.fee_schedule_id is None


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_upgrade_keeps_v2_untouched_and_is_a_no_op_without_v1(migrate_back):
    old = migrate_back(LEAF_0004)
    OldFeeSchedule = old.get_model("fees", "FeeSchedule")
    assert not OldFeeSchedule.objects.filter(version=1).exists()
    before = (
        OldFeeSchedule.objects.filter(fiscal_year=2026)
        .values(
            "id", "version", "tier_fees", "admin_fee_base", "admin_fee_per_beneficiary", "is_active"
        )
        .get()
    )
    new = _migrate(LEAF_0006)
    assert (
        new.get_model("fees", "FeeSchedule")
        .objects.filter(fiscal_year=2026)
        .values(
            "id", "version", "tier_fees", "admin_fee_base", "admin_fee_per_beneficiary", "is_active"
        )
        .get()
        == before
    )


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_upgrade_refuses_while_another_legacy_schedule_exists(migrate_back):
    old = migrate_back(LEAF_0004)
    OldFeeSchedule = old.get_model("fees", "FeeSchedule")
    legacy_fy2025 = {**FY2026_V1, "fiscal_year": 2025, "admin_fee_formula": "FLAT"}
    OldFeeSchedule.objects.create(**legacy_fy2025)
    OldFeeSchedule.objects.create(**{**FY2026_V1, "is_active": False, "admin_fee_formula": "FLAT"})

    with pytest.raises(RuntimeError, match="FY2025 v1"):
        _migrate(LEAF_0006)

    # Nothing changed: FY 2026 v1 is still there, FY 2025 untouched, v2 still active.
    assert OldFeeSchedule.objects.filter(fiscal_year=2026, version=1).exists()
    assert OldFeeSchedule.objects.filter(fiscal_year=2025, admin_fee_formula="FLAT").exists()
    assert OldFeeSchedule.objects.get(fiscal_year=2026, is_active=True).version == 2
    OldFeeSchedule.objects.filter(fiscal_year=2025).delete()  # let the fixture migrate forward


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_upgrade_refuses_to_remove_an_active_v1(migrate_back):
    old = migrate_back(LEAF_0004)
    OldFeeSchedule = old.get_model("fees", "FeeSchedule")
    OldFeeSchedule.objects.filter(fiscal_year=2026).update(is_active=False)
    OldFeeSchedule.objects.create(**{**FY2026_V1, "admin_fee_formula": "FLAT"})  # active

    with pytest.raises(RuntimeError, match="still the active schedule"):
        _migrate(LEAF_0006)

    assert OldFeeSchedule.objects.get(fiscal_year=2026, is_active=True).version == 1
    OldFeeSchedule.objects.filter(fiscal_year=2026, version=1).update(is_active=False)
    OldFeeSchedule.objects.filter(fiscal_year=2026, version=2).update(is_active=True)


# --- migration 0008: FY 2026 version 3, every stored fee snapshot re-priced -------------------


def _priced_application(old_apps, schedule, **fields):
    """A submitted application priced on `schedule` with an outdated snapshot (v2 amounts)."""
    from apps.beneficiaries.factories import BeneficiaryFactory
    from apps.reference.constants import Kinship

    app = _application(**fields)
    BeneficiaryFactory(
        application=app, row_number=2, kinship=Kinship.SON_UNIVERSITY, full_name="يوسف",
        birth_year=2005,
    )  # fmt: skip
    old_apps.get_model("applications", "InsuranceApplication").objects.filter(pk=app.pk).update(
        fee_schedule_id=schedule.pk,
        fee_snapshot={**app.fee_snapshot, "schedule_id": str(schedule.pk)},
    )
    return app


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_upgrade_to_v3_reprices_every_snapshot_and_removes_v2(migrate_back):
    """The dev database path: fees at 0007, v2 active, locked and used by submissions."""
    from apps.applications.models import InsuranceApplication
    from apps.fees.services import quote_for_application

    old = migrate_back(LEAF_0007)
    OldFeeSchedule = old.get_model("fees", "FeeSchedule")
    v2 = OldFeeSchedule.objects.get(fiscal_year=2026, version=2)
    OldFeeSchedule.objects.filter(pk=v2.pk).update(locked_at=timezone.now())
    submitted = _priced_application(old, v2)
    approved = _priced_application(old, v2, reference_number="MED-2026-000778", status="APPROVED")
    draft = _application(reference_number=None, status="DRAFT", submitted_at=None)
    InsuranceApplication.objects.filter(pk=draft.pk).update(fee_snapshot=None)
    before = _fingerprint()

    _migrate(None)

    assert not FeeSchedule.objects.filter(pk=v2.pk).exists()
    v3 = FeeSchedule.objects.get(fiscal_year=2026)
    assert (v3.version, v3.is_active, v3.service_fee) == (3, True, 800)
    assert v3.tier_fees == FY2026_TIER_FEES
    assert v3.locked_at is not None  # used by the re-priced submissions
    for app in (submitted, approved):
        app.refresh_from_db()
        assert app.fee_schedule_id == v3.pk
        assert app.fee_snapshot == quote_for_application(app, schedule=v3).as_dict()
        # tier 3: member 825 + minor child 605 + university child priced as a child 605,
        # admin 200 + 175 × 3 = 725, service 800 (the old snapshot said 1925)
        assert app.fee_snapshot["total"] == 825 + 605 + 605 + 725 + 800
        assert app.fee_snapshot["breakdown"][-1] == {
            "label": "رسوم الخدمة", "fee": 800, "note": "",
        }  # fmt: skip
        assert app.fee_snapshot["schedule_id"] == str(v3.pk)
    draft.refresh_from_db()
    assert (draft.fee_snapshot, draft.fee_schedule_id) == (None, None)
    # Nothing else changed: other columns, beneficiaries, documents, audit entries.
    after = _fingerprint()
    for rows in (before["applications"], after["applications"]):
        for row in rows:
            row.pop("fee_snapshot")
            row.pop("fee_schedule_id")
    assert after == before


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_v3_migration_is_idempotent_and_leaves_other_fiscal_years_alone(migrate_back):
    from django.apps import apps as global_apps

    old = migrate_back(LEAF_0007)
    OldFeeSchedule = old.get_model("fees", "FeeSchedule")
    fy2027 = OldFeeSchedule.objects.create(
        fiscal_year=2027, version=1, is_active=True, tier_fees=FY2026_TIER_FEES,
        tier_boundaries=[5, 10, 15],
    )  # fmt: skip
    _migrate(None)
    v3 = FeeSchedule.objects.get(fiscal_year=2026)

    with transaction.atomic():
        V3_0008.forwards(global_apps, None)  # a second run changes nothing

    assert list(FeeSchedule.objects.filter(fiscal_year=2026)) == [v3]
    assert FeeSchedule.objects.get(pk=fy2027.pk).service_fee == 800  # column default only
    FeeSchedule.objects.filter(pk=fy2027.pk).delete()


def test_v3_migration_carries_its_own_frozen_amounts():
    assert V3_0008.FY2026_V3["tier_fees"] == FY2026_TIER_FEES
    assert (
        V3_0008.FY2026_V3["admin_fee_base"],
        V3_0008.FY2026_V3["admin_fee_per_beneficiary"],
        V3_0008.FY2026_V3["service_fee"],
    ) == (200, 175, 800)
