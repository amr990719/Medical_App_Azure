"""Validate the kinship CHECK constraint re-created NOT VALID in 0003.

VALIDATE takes SHARE UPDATE EXCLUSIVE (reads and writes continue). Non-atomic so the scan runs in
its own transaction and releases its lock as soon as it finishes.
"""

from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("beneficiaries", "0003_remove_daughter_kinship"),
    ]

    operations = [
        migrations.RunSQL(
            sql='ALTER TABLE "beneficiaries_beneficiary" VALIDATE CONSTRAINT '
            '"beneficiary_kinship_valid";',
            reverse_sql=migrations.RunSQL.noop,  # a validated constraint needs no undo
        ),
    ]
