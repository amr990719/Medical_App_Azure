"""Remove the standalone DAUGHTER kinship (owner requirement of 2026-10-28).

A read-only check of the dev database found no DAUGHTER rows (execution
`caj-medsyn-dev-migrate-5mm3rw5`). The CHECK constraint is re-created NOT VALID (no scan under the
ACCESS EXCLUSIVE lock, `lock_timeout` 2s so it fails fast instead of queueing) and validated in
0004 under SHARE UPDATE EXCLUSIVE. If a DAUGHTER row exists, 0004 fails and nothing is converted.
The previous revision never offers DAUGHTER; a crafted request to it after this migration gets a
constraint error instead of a stored row.
"""

from django.db import migrations, models

KINSHIPS = "'MOTHER', 'FATHER', 'SON_MINOR', 'SON_UNIVERSITY', 'SON_GRADUATE', 'HUSBAND', 'WIFE'"
OLD_KINSHIPS = (
    "'MOTHER', 'FATHER', 'SON_MINOR', 'SON_UNIVERSITY', 'SON_GRADUATE', 'DAUGHTER', 'HUSBAND', "
    "'WIFE'"
)
REPLACE_CONSTRAINT = """
SET LOCAL lock_timeout = '2s';
ALTER TABLE "beneficiaries_beneficiary" DROP CONSTRAINT "beneficiary_kinship_valid";
ALTER TABLE "beneficiaries_beneficiary" ADD CONSTRAINT "beneficiary_kinship_valid"
    CHECK (("kinship" = '' OR "kinship" IN ({kinships}))) NOT VALID;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("applications", "0001_initial"),
        ("beneficiaries", "0002_beneficiary_is_first_time"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=REPLACE_CONSTRAINT.format(kinships=KINSHIPS),
                    reverse_sql=REPLACE_CONSTRAINT.format(kinships=OLD_KINSHIPS),
                ),
            ],
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="beneficiary",
                    name="beneficiary_kinship_valid",
                ),
                migrations.AlterField(
                    model_name="beneficiary",
                    name="kinship",
                    field=models.CharField(
                        blank=True,
                        choices=[
                            ("MOTHER", "أم"),
                            ("FATHER", "أب"),
                            ("SON_MINOR", "ابن/ابنة (18 سنة أو أقل)"),
                            ("SON_UNIVERSITY", "ابن/ابنة (طالب جامعي)"),
                            ("SON_GRADUATE", "ابن/ابنة (خريج)"),
                            ("HUSBAND", "زوج"),
                            ("WIFE", "زوجة"),
                        ],
                        max_length=16,
                    ),
                ),
                migrations.AddConstraint(
                    model_name="beneficiary",
                    constraint=models.CheckConstraint(
                        condition=models.Q(
                            ("kinship", ""),
                            (
                                "kinship__in",
                                [
                                    "MOTHER",
                                    "FATHER",
                                    "SON_MINOR",
                                    "SON_UNIVERSITY",
                                    "SON_GRADUATE",
                                    "HUSBAND",
                                    "WIFE",
                                ],
                            ),
                            _connector="OR",
                        ),
                        name="beneficiary_kinship_valid",
                    ),
                ),
            ],
        ),
    ]
