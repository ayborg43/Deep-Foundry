from django.db import migrations

# Workspace-orchestration tools: let a coworker in chat report on the
# workspace (safe) and — behind the approval gate (sensitive) — create
# coworkers/teams, start team runs, assign background tasks, and schedule
# workflows. Executors live in ai.tool_executor / core.interface.

TOOLS = [
    ("workspace_status", "safe",
     "Read-only overview of this workspace: coworkers, agent teams with their latest run and results, recent tasks, and pending approvals.",
     {"type": "object", "properties": {}, "required": []}),
    ("create_coworker", "sensitive",
     "Create a new AI coworker in this workspace with a name, role description, and optional tool names.",
     {"type": "object",
      "properties": {"name": {}, "role_description": {}, "tools": {"type": "array"}},
      "required": ["name", "role_description"]}),
    ("create_agent_team", "sensitive",
     "Create an agent team from existing coworkers. members is a list of {coworker: name-or-id, role: manager|researcher|writer|reviewer|developer|tester|security_reviewer|architect|planner|product_manager|custom}.",
     {"type": "object",
      "properties": {"name": {}, "collaboration_pattern": {}, "members": {"type": "array"}},
      "required": ["name", "members"]}),
    ("run_agent_team", "sensitive",
     "Start an agent team run on an objective. team is the team's name or id.",
     {"type": "object", "properties": {"team": {}, "objective": {}},
      "required": ["team", "objective"]}),
    ("create_task", "sensitive",
     "Assign a background task to a coworker (by name or id) with a title and description; it runs autonomously.",
     {"type": "object", "properties": {"coworker": {}, "title": {}, "description": {}},
      "required": ["coworker", "title", "description"]}),
    ("schedule_workflow", "sensitive",
     "Create a workflow of coworker steps (each {coworker, title, instructions}) ending in a human checkpoint, optionally on a cron schedule.",
     {"type": "object",
      "properties": {"name": {}, "schedule_cron": {}, "steps": {"type": "array"}},
      "required": ["name", "steps"]}),
]


def seed(apps, schema_editor):
    Tool = apps.get_model("core", "Tool")
    for name, risk, description, input_schema in TOOLS:
        Tool.objects.update_or_create(name=name, defaults={
            "description": description,
            "risk_classification": risk,
            "provider": "built_in",
            "input_schema": input_schema,
            "output_schema": {"type": "object"},
        })


def unseed(apps, schema_editor):
    Tool = apps.get_model("core", "Tool")
    Tool.objects.filter(name__in=[name for name, *_ in TOOLS]).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0025_remove_demo_marketplace_packs")]
    operations = [migrations.RunPython(seed, unseed)]
