"""Remove the legacy administrative-fee formula (contract step of 0003).

After 0005 no schedule uses the FLAT formula, so its two amounts and the formula column go, and
`admin_fee_base` / `admin_fee_per_beneficiary` become NOT NULL (every remaining row has them).
A separate migration from 0005: PostgreSQL refuses ALTER TABLE in a transaction that still has
the deferred foreign-key checks of 0005's delete pending.

Reverse re-adds the columns (formula PER_BENEFICIARY, legacy amounts NULL) and the CHECK, which
every remaining row satisfies.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("fees", "0005_remove_fy2026_v1")]

    operations = [
        migrations.RemoveConstraint(
            model_name="feeschedule",
            name="fee_schedule_admin_fee_formula_complete",
        ),
        migrations.RemoveField(model_name="feeschedule", name="admin_fee_formula"),
        migrations.RemoveField(model_name="feeschedule", name="admin_fee_member_only"),
        migrations.RemoveField(model_name="feeschedule", name="admin_fee_with_beneficiaries"),
        migrations.AlterField(
            model_name="feeschedule",
            name="admin_fee_base",
            field=models.PositiveIntegerField(default=200),
        ),
        migrations.AlterField(
            model_name="feeschedule",
            name="admin_fee_per_beneficiary",
            field=models.PositiveIntegerField(default=175),
        ),
    ]
