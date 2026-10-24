"""Remove FY 2026 schedule version 1 (the original four-tier seed of 0002) — owner, 2026-10-24.

0002 stays as migration history; this migration deletes the row it created, identified only by
`fiscal_year=2026, version=1`. Version 2 (0004) and every later version are kept.

Applications priced with version 1 keep their `fee_snapshot` and `submitted_snapshot` exactly —
they are the record of what was charged. Only their `fee_schedule` reference (nullable, PROTECT)
is cleared, with a queryset UPDATE so no other column (not even `updated_at`) changes. They are
never re-priced or pointed at version 2: that would misrepresent the schedule they used. The
snapshot's own `schedule_id` and the audit entries keep the removed version's id as history.

Refuses to run (changing nothing) when:
* another schedule still uses the legacy format (tiers 1-4 or the FLAT administrative fee) —
  0006 removes that support, and converting it would mean inventing tier 0 amounts or changing
  its administrative fee, which needs an explicit owner decision;
* version 1 is still the ACTIVE FY 2026 schedule — removing it would leave the year unpriced.

Idempotent (nothing to do once version 1 is gone). Reverse is a no-op: version 1 is not
recreated, and the cleared references cannot be told apart from never-submitted applications.
"""

from django.db import migrations

V1 = {"fiscal_year": 2026, "version": 1}
TIERS = {"0", "1", "2", "3", "4"}


def _label(schedule) -> str:
    return f"FY{schedule.fiscal_year} v{schedule.version}"


def forwards(apps, schema_editor):
    FeeSchedule = apps.get_model("fees", "FeeSchedule")
    InsuranceApplication = apps.get_model("applications", "InsuranceApplication")

    legacy = [
        _label(s)
        for s in FeeSchedule.objects.exclude(**V1).order_by("fiscal_year", "version")
        if s.admin_fee_formula != "PER_BENEFICIARY" or set(s.tier_fees) != TIERS
    ]
    if legacy:
        raise RuntimeError(
            "Legacy-format fee schedules other than FY2026 v1 exist: "
            + ", ".join(legacy)
            + ". Convert or remove them explicitly before removing legacy support (fees.0006)."
        )

    v1 = FeeSchedule.objects.select_for_update().filter(**V1).first()
    if v1 is None:
        return
    if v1.is_active:
        raise RuntimeError(
            "FY2026 v1 is still the active schedule; activate version 2 (fees.0004) first."
        )
    InsuranceApplication.objects.filter(fee_schedule_id=v1.pk).update(fee_schedule=None)
    FeeSchedule.objects.filter(pk=v1.pk).delete()  # historical model: no lock guard


class Migration(migrations.Migration):
    dependencies = [
        ("fees", "0004_fy2026_v2_schedule"),
        ("applications", "0001_initial"),
    ]

    operations = [migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop)]
