from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ai", "0005_message_uniq_tool_result_per_call")]

    operations = [
        migrations.AddIndex(
            model_name="modelcall",
            index=models.Index(
                fields=["workspace", "created_at"],
                name="model_calls_workspa_1dfa76_idx",
            ),
        )
    ]
