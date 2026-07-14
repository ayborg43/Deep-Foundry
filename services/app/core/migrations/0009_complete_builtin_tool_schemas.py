from django.db import migrations


def update_schemas(apps, schema_editor):
    Tool = apps.get_model("core", "Tool")
    Tool.objects.filter(name="web_search", provider="built_in").update(
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "maxLength": 500},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "url": {"type": "string"},
                            "snippet": {"type": "string"},
                        },
                    },
                }
            },
        },
    )
    Tool.objects.filter(name="execute_code", provider="built_in").update(
        input_schema={
            "type": "object",
            "properties": {
                "language": {"type": "string", "enum": ["python"]},
                "code": {"type": "string"},
            },
            "required": ["language", "code"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
                "exit_code": {"type": ["integer", "null"]},
                "truncated": {"type": "boolean"},
            },
        },
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0008_audit_log_immutable")]
    operations = [migrations.RunPython(update_schemas, migrations.RunPython.noop)]
