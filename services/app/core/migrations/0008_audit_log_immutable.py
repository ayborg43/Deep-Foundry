from django.db import migrations


CREATE_IMMUTABILITY_TRIGGER = """
CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only; % is not permitted', TG_OP
        USING ERRCODE = '55000';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_immutable
BEFORE UPDATE OR DELETE ON audit_log
FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();
"""

DROP_IMMUTABILITY_TRIGGER = """
DROP TRIGGER IF EXISTS audit_log_immutable ON audit_log;
DROP FUNCTION IF EXISTS prevent_audit_log_mutation();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0007_task_notification")]

    operations = [
        migrations.RunSQL(
            sql=CREATE_IMMUTABILITY_TRIGGER,
            reverse_sql=DROP_IMMUTABILITY_TRIGGER,
        )
    ]
