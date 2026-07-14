from django.db import migrations


MODEL_REPLACEMENTS = {
    "deepseek-4": "deepseek-v4-flash",
    "deepseek-chat": "deepseek-v4-flash",
    "deepseek-reasoner": "deepseek-v4-pro",
}


def update_model_bindings(apps, schema_editor):
    CoworkerVersion = apps.get_model("core", "CoworkerVersion")

    for version in CoworkerVersion.objects.all().iterator():
        binding = dict(version.model_binding or {})
        changed = False

        primary = binding.get("primary")
        if primary in MODEL_REPLACEMENTS:
            binding["primary"] = MODEL_REPLACEMENTS[primary]
            changed = True

        fallback = binding.get("fallback")
        if isinstance(fallback, list):
            updated_fallback = [MODEL_REPLACEMENTS.get(model_id, model_id) for model_id in fallback]
            if updated_fallback != fallback:
                binding["fallback"] = updated_fallback
                changed = True

        if changed:
            version.model_binding = binding
            version.save(update_fields=["model_binding"])


class Migration(migrations.Migration):
    dependencies = [("core", "0016_consensussession_voicesession_voiceturn_and_more")]
    operations = [migrations.RunPython(update_model_bindings, migrations.RunPython.noop)]
