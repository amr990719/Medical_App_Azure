"""Make audit_auditlog append-only at the database level (PROMPT.md §39).

A BEFORE UPDATE OR DELETE row trigger raises for every client, not only the Django ORM.
TRUNCATE (used by the test runner to reset transactional tests) is unaffected.
The table is new and empty, so CREATE TRIGGER takes its lock for milliseconds only.
"""

from django.db import migrations

FORWARD = """
CREATE FUNCTION audit_auditlog_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_auditlog is append-only (% refused)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$;

CREATE TRIGGER audit_auditlog_append_only
BEFORE UPDATE OR DELETE ON audit_auditlog
FOR EACH ROW EXECUTE FUNCTION audit_auditlog_append_only();
"""

REVERSE = """
DROP TRIGGER IF EXISTS audit_auditlog_append_only ON audit_auditlog;
DROP FUNCTION IF EXISTS audit_auditlog_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, reverse_sql=REVERSE)]
