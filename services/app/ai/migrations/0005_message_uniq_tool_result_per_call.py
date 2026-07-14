from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ai", "0004_memory_and_knowledge")]

    operations = [
        migrations.AddConstraint(
            model_name="message",
            constraint=models.UniqueConstraint(
                condition=models.Q(("tool_call_id__isnull", False)),
                fields=("parent_message", "tool_call_id"),
                name="uniq_tool_result_per_call",
            ),
        )
    ]
