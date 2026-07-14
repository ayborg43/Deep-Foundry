from django.db import migrations


TOOLS = [
    ("create_presentation", "Create a structured presentation artifact from a title and slide content.", "presentation"),
    ("create_diagram", "Create a Mermaid-compatible diagram artifact.", "diagram"),
    ("record_video_analysis", "Store a structured video analysis with observations and timestamps.", "video_analysis"),
]


def seed(apps, schema_editor):
    Tool = apps.get_model("core", "Tool")
    for name, description, artifact_type in TOOLS:
        Tool.objects.update_or_create(name=name, defaults={
            "description": description, "risk_classification": "safe", "provider": "built_in",
            "input_schema": {"type": "object", "properties": {"name": {"type": "string"}, "content": {"type": "object"}}, "required": ["name", "content"]},
            "output_schema": {"type": "object", "properties": {"artifact_id": {"type": "string"}, "checksum": {"type": "string"}}},
        })


class Migration(migrations.Migration):
    dependencies = [("core", "0014_backfill_marketplace_security_reviews")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
