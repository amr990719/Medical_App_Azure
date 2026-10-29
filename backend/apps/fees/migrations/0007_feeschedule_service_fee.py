"""Service fee (رسوم الخدمة): a fixed amount per application, stored on the schedule version.

`db_default` 800 so the previous revision's inserts (an admin creating a version) still work
while it runs next to this schema; adding a column with a constant default is a catalog-only
change on PostgreSQL 11+, still under ACCESS EXCLUSIVE, hence the 2s `lock_timeout`.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("fees", "0006_remove_legacy_admin_fee")]

    operations = [
        migrations.RunSQL("SET LOCAL lock_timeout = '2s';", reverse_sql=migrations.RunSQL.noop),
        migrations.AddField(
            model_name="feeschedule",
            name="service_fee",
            field=models.PositiveIntegerField(db_default=800, default=800),
        ),
    ]
