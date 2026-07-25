from django.db import migrations

# 0031 seeded Free at max_coworkers=2, which is smaller than the built-in
# "software" starter template (4 coworkers: Tech Lead, Developer, Code
# Reviewer, Tester) — a first-time Free user couldn't provision the
# platform's own default template. Room for one full starter team plus a
# bit of headroom, still clearly a "free" tier next to Pro/Enterprise.
NEW_LIMITS = {"max_coworkers": 5, "max_agent_teams": 2, "max_tasks_per_month": 50, "max_seats": 3}


def raise_limits(apps, schema_editor):
    SubscriptionPlan = apps.get_model("core", "SubscriptionPlan")
    SubscriptionPlan.objects.filter(key="free").update(**NEW_LIMITS)


def revert_limits(apps, schema_editor):
    SubscriptionPlan = apps.get_model("core", "SubscriptionPlan")
    SubscriptionPlan.objects.filter(key="free").update(
        max_coworkers=2, max_agent_teams=1, max_tasks_per_month=20, max_seats=3
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0032_subscription_plan_fk")]
    operations = [migrations.RunPython(raise_limits, revert_limits)]
