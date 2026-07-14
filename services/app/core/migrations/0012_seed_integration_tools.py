from django.db import migrations


TOOLS = [
    ("send_email", "Send an email through the workspace email integration.", ["to", "subject", "body"]),
    ("create_calendar_event", "Create an event through the workspace calendar integration.", ["title", "starts_at"]),
    ("send_slack_message", "Send a message through the workspace Slack integration.", ["text"]),
    ("send_discord_message", "Send a message through the workspace Discord integration.", ["content"]),
    ("create_github_issue", "Create an issue through the workspace GitHub integration.", ["title", "body"]),
    ("send_webhook", "POST a payload through the workspace generic webhook integration.", ["payload"]),
]


def seed(apps, schema_editor):
    Tool = apps.get_model("core", "Tool")
    for name, description, required in TOOLS:
        Tool.objects.update_or_create(name=name, defaults={
            "description": description,
            "risk_classification": "dangerous",
            "provider": "built_in",
            "input_schema": {"type": "object", "properties": {key: {} for key in required}, "required": required},
            "output_schema": {"type": "object"},
        })


class Migration(migrations.Migration):
    dependencies = [("core", "0011_seed_v2_capability_packs")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
