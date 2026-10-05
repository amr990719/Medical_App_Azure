"""Seed the FY 2026 fee schedule (PROMPT.md §17.1).

The amounts are inlined on purpose: a data migration must not import application code that may
change after this migration is applied. Reversible: the reverse removes the row only while no
application references it (PROTECT would refuse otherwise) and it is not locked.
"""

from django.db import migrations

FY2026 = {
    "fiscal_year": 2026,
    "version": 1,
    "tier_fees": {
        "1": {"member": 600, "spouse": 800, "child": 500, "grad_son": 1200, "parent": 1050},
        "2": {"member": 700, "spouse": 950, "child": 550, "grad_son": 1400, "parent": 1200},
        "3": {"member": 750, "spouse": 1000, "child": 550, "grad_son": 1500, "parent": 1300},
        "4": {"member": 850, "spouse": 1050, "child": 600, "grad_son": 1750, "parent": 1400},
    },
    "tier_boundaries": [5, 10, 15],
    "admin_fee_member_only": 150,
    "admin_fee_with_beneficiaries": 175,
    "age_cap_threshold": 70,
    "age_cap_amount": 500,
    "registration_year_min": 1950,
    "is_active": True,
}


def seed(apps, schema_editor):
    FeeSchedule = apps.get_model("fees", "FeeSchedule")
    lookup = {"fiscal_year": FY2026["fiscal_year"], "version": FY2026["version"]}
    defaults = {k: v for k, v in FY2026.items() if k not in lookup}
    FeeSchedule.objects.get_or_create(**lookup, defaults=defaults)


def unseed(apps, schema_editor):
    FeeSchedule = apps.get_model("fees", "FeeSchedule")
    FeeSchedule.objects.filter(
        fiscal_year=FY2026["fiscal_year"], version=FY2026["version"], locked_at__isnull=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("fees", "0001_initial")]

    operations = [migrations.RunPython(seed, reverse_code=unseed)]
