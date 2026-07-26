from django.db import migrations

# send_telegram: deliver a message to the linked Telegram chats of the
# workspace's members. Classified `safe` (not `dangerous` like send_email) on
# purpose — it can only reach chats a user themselves verified with the bot, so
# it can run unattended (e.g. a scheduled news digest) without a per-send
# approval. The executor lives in ai.tool_executor / core.interface.
#
# This migration also re-seeds schedule_workflow with a require_review flag, so
# a coworker can set up an unattended notification schedule (news every hour)
# without appending a human checkpoint that would demand an approval each run.

SEND_TELEGRAM = {
    "name": "send_telegram",
    "risk_classification": "safe",
    "description": (
        "Send a message to the Telegram chats of workspace members who have "
        "linked their account. Ideal for delivering news, alerts, or updates — "
        "including on a schedule. Reaches only chats users verified with the "
        "bot, never an arbitrary number."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "The message to send."}},
        "required": ["text"],
    },
    "output_schema": {"type": "object"},
}

SCHEDULE_WORKFLOW = {
    "name": "schedule_workflow",
    "risk_classification": "sensitive",
    "description": (
        "Create a workflow of coworker steps (each {coworker, title, "
        "instructions}), optionally on a cron schedule (standard 5-field cron, "
        "evaluated every minute — so '* * * * *' runs every minute, '0 * * * *' "
        "hourly, '0 8 * * *' daily at 08:00). Ends in a human review checkpoint "
        "unless require_review is false — set it false for unattended "
        "notification jobs like sending news on a schedule."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {},
            "schedule_cron": {},
            "steps": {"type": "array"},
            "require_review": {"type": "boolean"},
        },
        "required": ["name", "steps"],
    },
    "output_schema": {"type": "object"},
}


def seed(apps, schema_editor):
    Tool = apps.get_model("core", "Tool")
    for tool in (SEND_TELEGRAM, SCHEDULE_WORKFLOW):
        Tool.objects.update_or_create(
            name=tool["name"],
            defaults={
                "description": tool["description"],
                "risk_classification": tool["risk_classification"],
                "provider": "built_in",
                "input_schema": tool["input_schema"],
                "output_schema": tool["output_schema"],
            },
        )


def unseed(apps, schema_editor):
    Tool = apps.get_model("core", "Tool")
    Tool.objects.filter(name="send_telegram").delete()
    # Restore schedule_workflow's prior schema (without require_review).
    Tool.objects.filter(name="schedule_workflow").update(
        description=(
            "Create a workflow of coworker steps (each {coworker, title, "
            "instructions}) ending in a human checkpoint, optionally on a cron "
            "schedule."
        ),
        input_schema={
            "type": "object",
            "properties": {"name": {}, "schedule_cron": {}, "steps": {"type": "array"}},
            "required": ["name", "steps"],
        },
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0034_alter_notification_type_alter_task_status")]
    operations = [migrations.RunPython(seed, unseed)]
