"""Remove the treatment card number (بطاقة العلاج; owner requirement of 2026-10-29).

The form shows the existing syndicate registration year in its place, so nothing replaces the
column. Dropping a column is a catalog-only change on PostgreSQL but takes ACCESS EXCLUSIVE, hence
the 2s `lock_timeout`. Expand and contract ship together (as D163): the previous revision selects
this column, so between the migrate job and the new revision its doctor-profile reads fail
(fail-closed, nothing is written wrongly). Reverse re-adds the column empty.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("doctors", "0001_initial")]

    operations = [
        migrations.RunSQL("SET LOCAL lock_timeout = '2s';", reverse_sql=migrations.RunSQL.noop),
        migrations.RemoveField(model_name="doctor", name="treatment_card_number"),
    ]
