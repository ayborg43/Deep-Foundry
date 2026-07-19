from django.db import migrations


def seed(apps, schema_editor):
    Tool = apps.get_model("core", "Tool")
    Tool.objects.update_or_create(name="post_tweet", defaults={
        "description": "Post a tweet through the workspace Twitter / X integration.",
        "risk_classification": "dangerous",
        "provider": "built_in",
        "input_schema": {
            "type": "object",
            "properties": {"text": {}, "in_reply_to_tweet_id": {}},
            "required": ["text"],
        },
        "output_schema": {"type": "object"},
    })


def unseed(apps, schema_editor):
    Tool = apps.get_model("core", "Tool")
    Tool.objects.filter(name="post_tweet").delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0023_integration_twitter_kind")]
    operations = [migrations.RunPython(seed, unseed)]
