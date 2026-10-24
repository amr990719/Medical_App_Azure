"""FY 2026 schedule version 2: tier 0 and the per-beneficiary administrative fee.

Fresh and existing databases both end with this version ACTIVE for FY 2026. The previous active
version is only deactivated (`is_active=False`): its amounts — and every submitted application's
`fee_snapshot` and `fee_schedule` reference — stay untouched.

The amounts are inlined on purpose (a data migration must not import application code), and
`seed_dev_data` imports `FY2026_V2` from here so development seeding never recreates obsolete
pricing. Idempotent: does nothing when an active FY 2026 version already has these amounts.

Reverse: removes version 2 and reactivates the latest remaining version, refused once version 2
was used by a submission (locked) — that history cannot be undone.
"""

from django.db import migrations
from django.db.models import Max

FY2026_V2 = {
    "fiscal_year": 2026,
    "tier_fees": {
        "0": {"member": 400, "spouse": 880, "child": 550, "grad_son": None, "parent": 1155},
        "1": {"member": 660, "spouse": 880, "child": 550, "grad_son": 1320, "parent": 1155},
        "2": {"member": 770, "spouse": 1045, "child": 605, "grad_son": 1540, "parent": 1320},
        "3": {"member": 825, "spouse": 1100, "child": 605, "grad_son": 1650, "parent": 1430},
        "4": {"member": 935, "spouse": 1155, "child": 660, "grad_son": 1925, "parent": 1540},
    },
    "tier_boundaries": [5, 10, 15],
    "admin_fee_formula": "PER_BENEFICIARY",
    "admin_fee_base": 200,
    "admin_fee_per_beneficiary": 175,
    "admin_fee_member_only": None,
    "admin_fee_with_beneficiaries": None,
    "age_cap_threshold": 70,
    "age_cap_amount": 500,
    "registration_year_min": 1950,
}

_IDENTITY = ("fiscal_year", "tier_fees", "admin_fee_formula", "admin_fee_base",
             "admin_fee_per_beneficiary")  # fmt: skip


def _v2(FeeSchedule):
    return FeeSchedule.objects.filter(**{k: FY2026_V2[k] for k in _IDENTITY})


def forwards(apps, schema_editor):
    FeeSchedule = apps.get_model("fees", "FeeSchedule")
    fiscal_year = FY2026_V2["fiscal_year"]
    if _v2(FeeSchedule).filter(is_active=True).exists():
        return
    existing = FeeSchedule.objects.select_for_update().filter(fiscal_year=fiscal_year)
    latest = existing.aggregate(v=Max("version"))["v"] or 0
    existing.filter(is_active=True).update(is_active=False)  # amounts untouched, lock kept
    FeeSchedule.objects.create(**FY2026_V2, version=latest + 1, is_active=True)


def backwards(apps, schema_editor):
    FeeSchedule = apps.get_model("fees", "FeeSchedule")
    v2 = _v2(FeeSchedule)
    if v2.filter(locked_at__isnull=False).exists():
        raise RuntimeError(
            "FY 2026 schedule version 2 is used by a submission; it cannot be removed."
        )
    v2.delete()
    remaining = FeeSchedule.objects.filter(fiscal_year=FY2026_V2["fiscal_year"])
    if not remaining.filter(is_active=True).exists():
        latest = remaining.order_by("-version").first()
        if latest is not None:
            remaining.filter(pk=latest.pk).update(is_active=True)


class Migration(migrations.Migration):
    dependencies = [("fees", "0003_admin_fee_formula")]

    operations = [migrations.RunPython(forwards, reverse_code=backwards)]
