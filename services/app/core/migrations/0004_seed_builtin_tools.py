import uuid

from django.db import migrations

# Per IMPLEMENTATION_PLAN.md Milestone 3 Epic 3.2: web search, file
# read/write, and code execution — represented as 4 distinct tools so risk
# classification (SECURITY.md §4) has a real example of each tier before
# Milestone 4 wires up actual enforcement.
BUILTIN_TOOLS = [
    {
        "name": "web_search",
        "description": "Search the web and return summarized results with source links.",
        "risk_classification": "safe",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        "output_schema": {
            "type": "object",
            "properties": {"results": {"type": "array"}},
        },
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file within a granted folder.",
        "risk_classification": "safe",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        "output_schema": {
            "type": "object",
            "properties": {"content": {"type": "string"}},
        },
    },
    {
        "name": "write_file",
        "description": "Write or overwrite a file within a granted folder.",
        "risk_classification": "sensitive",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
        "output_schema": {
            "type": "object",
            "properties": {"bytes_written": {"type": "integer"}},
        },
    },
    {
        "name": "execute_code",
        "description": "Execute code in a sandboxed, ephemeral container (SECURITY.md §5).",
        "risk_classification": "dangerous",
        "input_schema": {
            "type": "object",
            "properties": {"language": {"type": "string"}, "code": {"type": "string"}},
            "required": ["language", "code"],
        },
        "output_schema": {
            "type": "object",
            "properties": {"stdout": {"type": "string"}, "stderr": {"type": "string"}},
        },
    },
]


def seed_tools(apps, schema_editor):
    Tool = apps.get_model("core", "Tool")
    for tool in BUILTIN_TOOLS:
        Tool.objects.get_or_create(
            name=tool["name"],
            defaults={
                "id": uuid.uuid7(),
                "description": tool["description"],
                "risk_classification": tool["risk_classification"],
                "input_schema": tool["input_schema"],
                "output_schema": tool["output_schema"],
                "provider": "built_in",
            },
        )


def unseed_tools(apps, schema_editor):
    Tool = apps.get_model("core", "Tool")
    Tool.objects.filter(name__in=[t["name"] for t in BUILTIN_TOOLS], provider="built_in").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_tool_coworker_coworkerversion_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_tools, reverse_code=unseed_tools),
    ]
