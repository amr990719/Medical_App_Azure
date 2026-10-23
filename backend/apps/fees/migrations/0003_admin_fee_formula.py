"""Administrative fee formula (FY 2026 version 2) — expand only.

* `admin_fee_formula` is added with default FLAT so every EXISTING schedule keeps its legacy rule
  (150 member only / 175 with beneficiaries); the field default then becomes PER_BENEFICIARY for
  new versions.
* `admin_fee_base` / `admin_fee_per_beneficiary` are added NULL for existing rows (they never had
  those amounts); new versions default to 200 / 175.
* The legacy FLAT amounts become nullable (NULL on PER_BENEFICIARY schedules). DROP NOT NULL is
  a catalog-only change on PostgreSQL.
* A CHECK keeps each formula's amounts present. Existing rows are FLAT with both legacy amounts,
  so validating it scans a handful of rows.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("fees", "0002_seed_fy2026")]

    operations = [
        migrations.AddField(
            model_name="feeschedule",
            name="admin_fee_formula",
            field=models.CharField(
                choices=[
                    ("FLAT", "ثابتة حسب وجود مستفيدين"),
                    ("PER_BENEFICIARY", "ثابتة + لكل مستفيد"),
                ],
                default="FLAT",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="feeschedule",
            name="admin_fee_formula",
            field=models.CharField(
                choices=[
                    ("FLAT", "ثابتة حسب وجود مستفيدين"),
                    ("PER_BENEFICIARY", "ثابتة + لكل مستفيد"),
                ],
                default="PER_BENEFICIARY",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="feeschedule",
            name="admin_fee_base",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="feeschedule",
            name="admin_fee_base",
            field=models.PositiveIntegerField(blank=True, default=200, null=True),
        ),
        migrations.AddField(
            model_name="feeschedule",
            name="admin_fee_per_beneficiary",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="feeschedule",
            name="admin_fee_per_beneficiary",
            field=models.PositiveIntegerField(blank=True, default=175, null=True),
        ),
        migrations.AlterField(
            model_name="feeschedule",
            name="admin_fee_member_only",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="feeschedule",
            name="admin_fee_with_beneficiaries",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="feeschedule",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("admin_fee_formula", "FLAT"),
                        ("admin_fee_member_only__isnull", False),
                        ("admin_fee_with_beneficiaries__isnull", False),
                    ),
                    models.Q(
                        ("admin_fee_base__isnull", False),
                        ("admin_fee_formula", "PER_BENEFICIARY"),
                        ("admin_fee_per_beneficiary__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="fee_schedule_admin_fee_formula_complete",
            ),
        ),
    ]
