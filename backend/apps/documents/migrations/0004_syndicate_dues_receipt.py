"""Document type SYNDICATE_DUES_RECEIPT (additional syndicate dues, apps.dues).

Each dues receipt is its own submission and is never replaced, so the type is excluded from the
one-active-document-per-slot unique index, and the owner check allows it without a beneficiary.
Expand-only: both constraints get looser, so the previous revision keeps working on the new
schema. Recreating the unique index locks `documents_document` for writes while it builds (a
small table); the 2s `lock_timeout` fails the deployment fast instead of queueing behind traffic.
"""

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("applications", "0001_initial"),
        ("beneficiaries", "0004_validate_kinship_constraint"),
        ("documents", "0003_document_types_id_back_photo_member_certificate"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunSQL("SET LOCAL lock_timeout = '2s';", reverse_sql=migrations.RunSQL.noop),
        migrations.RemoveConstraint(
            model_name="document",
            name="uniq_active_document_per_slot",
        ),
        migrations.RemoveConstraint(
            model_name="document",
            name="document_type_matches_owner",
        ),
        migrations.AlterField(
            model_name="document",
            name="document_type",
            field=models.CharField(
                choices=[
                    ("NATIONAL_ID_FRONT", "صورة البطاقة (وجه)"),
                    ("NATIONAL_ID_BACK", "صورة البطاقة (ظهر)"),
                    ("SYNDICATE_ID", "كارنيه النقابة"),
                    ("PERSONAL_PHOTO", "صورة العضو الأصلي"),
                    ("PAYMENT_RECEIPT", "إيصال الدفع"),
                    (
                        "MEMBER_BIRTH_CERTIFICATE",
                        "شهادة ميلاد العضو الأصلي لإثبات صلة القرابة بالأم",
                    ),
                    ("BENEFICIARY_NATIONAL_ID", "بطاقة الرقم القومي للمستفيد (وجه)"),
                    ("BENEFICIARY_NATIONAL_ID_BACK", "بطاقة الرقم القومي للمستفيد (ظهر)"),
                    ("BENEFICIARY_PERSONAL_PHOTO", "صورة شخصية للمستفيد بخلفية بيضاء"),
                    ("BIRTH_CERTIFICATE", "شهادة ميلاد المستفيد"),
                    ("MARRIAGE_CERTIFICATE", "شهادة الزواج"),
                    ("INSURANCE_PRINT", "برينت تأميني"),
                    ("UNIVERSITY_ID", "كارنيه الجامعة"),
                    ("OTHER", "مستند آخر"),
                    ("SYNDICATE_DUES_RECEIPT", "إيصال سداد مستحقات نقابية"),
                ],
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name="document",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("deleted_at__isnull", True),
                    models.Q(("document_type", "SYNDICATE_DUES_RECEIPT"), _negated=True),
                ),
                fields=("application", "beneficiary", "document_type"),
                name="uniq_active_document_per_slot",
                nulls_distinct=False,
            ),
        ),
        migrations.AddConstraint(
            model_name="document",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("deleted_at__isnull", False),
                    models.Q(
                        ("beneficiary__isnull", True),
                        (
                            "document_type__in",
                            (
                                "NATIONAL_ID_FRONT",
                                "NATIONAL_ID_BACK",
                                "SYNDICATE_ID",
                                "PERSONAL_PHOTO",
                                "PAYMENT_RECEIPT",
                                "MEMBER_BIRTH_CERTIFICATE",
                            ),
                        ),
                    ),
                    models.Q(
                        ("beneficiary__isnull", False),
                        (
                            "document_type__in",
                            (
                                "BENEFICIARY_NATIONAL_ID",
                                "BENEFICIARY_NATIONAL_ID_BACK",
                                "BIRTH_CERTIFICATE",
                                "MARRIAGE_CERTIFICATE",
                                "INSURANCE_PRINT",
                                "UNIVERSITY_ID",
                                "BENEFICIARY_PERSONAL_PHOTO",
                            ),
                        ),
                    ),
                    models.Q(
                        ("beneficiary__isnull", True), ("document_type", "SYNDICATE_DUES_RECEIPT")
                    ),
                    ("document_type", "OTHER"),
                    _connector="OR",
                ),
                name="document_type_matches_owner",
            ),
        ),
    ]
