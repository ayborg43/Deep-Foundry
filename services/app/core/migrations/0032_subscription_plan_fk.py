import django.db.models.deletion
from django.db import migrations, models

# Legacy Workspace.PlanTier value -> new SubscriptionPlan.key. Workspace.plan_tier
# itself is untouched (it's the self-hosted/cloud deployment marker); only
# Subscription's billing/limits plan moves from a fixed enum to the catalog.
TIER_TO_PLAN_KEY = {
    "self_hosted_free": "free",
    "cloud_free": "free",
    "cloud_pro": "pro",
    "cloud_enterprise": "enterprise",
}


def backfill_plan(apps, schema_editor):
    Subscription = apps.get_model("core", "Subscription")
    SubscriptionPlan = apps.get_model("core", "SubscriptionPlan")
    plans_by_key = {plan.key: plan for plan in SubscriptionPlan.objects.all()}
    default_plan = next((p for p in plans_by_key.values() if p.is_default), None) or plans_by_key.get("free")
    for subscription in Subscription.objects.all():
        key = TIER_TO_PLAN_KEY.get(subscription.plan_tier)
        subscription.plan = plans_by_key.get(key) or default_plan
        subscription.save(update_fields=["plan"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0031_subscriptionplan"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscription",
            name="plan",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="subscriptions",
                to="core.subscriptionplan",
            ),
        ),
        migrations.RunPython(backfill_plan, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="subscription",
            name="plan",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="subscriptions",
                to="core.subscriptionplan",
            ),
        ),
        migrations.RemoveField(
            model_name="subscription",
            name="plan_tier",
        ),
    ]
