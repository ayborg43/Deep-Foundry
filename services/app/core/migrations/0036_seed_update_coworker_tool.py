from django.db import migrations

# update_coworker: edit an existing coworker from chat — rename it, rewrite its
# role, switch model, or add/remove tools. Sensitive, so it goes through the
# approval gate. A coworker passes its own name to edit itself. Executor lives
# in ai.tool_executor -> core.interface.orchestrate_update_coworker.

TOOL = {
    "name": "update_coworker",
    "risk_classification": "sensitive",
    "description": (
        "Update an existing coworker in this workspace. `coworker` is its name "
        "or id (pass your own name to edit yourself). Provide only the fields to "
        "change: name, role_description (the full replacement text), model, "
        "add_tools, remove_tools. Role/model changes are versioned, so nothing "
        "is lost."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "coworker": {},
            "name": {},
            "role_description": {},
            "model": {},
            "add_tools": {"type": "array"},
            "remove_tools": {"type": "array"},
        },
        "required": ["coworker"],
    },
    "output_schema": {"type": "object"},
}


def seed(apps, schema_editor):
    Tool = apps.get_model("core", "Tool")
    Tool.objects.update_or_create(
        name=TOOL["name"],
        defaults={
            "description": TOOL["description"],
            "risk_classification": TOOL["risk_classification"],
            "provider": "built_in",
            "input_schema": TOOL["input_schema"],
            "output_schema": TOOL["output_schema"],
        },
    )


def unseed(apps, schema_editor):
    Tool = apps.get_model("core", "Tool")
    Tool.objects.filter(name="update_coworker").delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0035_seed_send_telegram_tool")]
    operations = [migrations.RunPython(seed, unseed)]
