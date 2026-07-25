import uuid

from django.db import migrations, models

# Seed catalog: Free is the plan every new workspace lands on
# (SubscriptionPlan.is_default / core.provisioning). Limits are counts;
# None means unlimited. Deliberately conservative starting numbers —
# platform staff can edit all of this from the admin plan catalog.
PLANS = [
    {
        "key": "free", "name": "Free", "sort_order": 0, "price_usd": "0.00",
        "description": "Get started with a small team of AI coworkers.",
        "max_coworkers": 2, "max_agent_teams": 1, "max_tasks_per_month": 20,
        "max_seats": 3, "is_default": True,
    },
    {
        "key": "pro", "name": "Pro", "sort_order": 1, "price_usd": "49.00",
        "description": "More coworkers, teams, and monthly runs for growing teams.",
        "max_coworkers": 10, "max_agent_teams": 5, "max_tasks_per_month": 300,
        "max_seats": 15, "is_default": False,
    },
    {
        "key": "enterprise", "name": "Enterprise", "sort_order": 2, "price_usd": "0.00",
        "description": "Unlimited coworkers, teams, and usage. Contact sales.",
        "max_coworkers": None, "max_agent_teams": None, "max_tasks_per_month": None,
        "max_seats": None, "is_default": False,
    },
]


def seed_plans(apps, schema_editor):
    SubscriptionPlan = apps.get_model("core", "SubscriptionPlan")
    for plan in PLANS:
        SubscriptionPlan.objects.update_or_create(key=plan["key"], defaults=plan)


def unseed_plans(apps, schema_editor):
    SubscriptionPlan = apps.get_model("core", "SubscriptionPlan")
    SubscriptionPlan.objects.filter(key__in=[p["key"] for p in PLANS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0030_telegramconnection_telegramdelivery_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="SubscriptionPlan",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("key", models.SlugField(max_length=50, unique=True)),
                ("name", models.CharField(max_length=100)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("price_usd", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("max_coworkers", models.PositiveIntegerField(blank=True, null=True)),
                ("max_agent_teams", models.PositiveIntegerField(blank=True, null=True)),
                ("max_tasks_per_month", models.PositiveIntegerField(blank=True, null=True)),
                ("max_seats", models.PositiveIntegerField(blank=True, null=True)),
                ("is_default", models.BooleanField(default=False)),
                ("active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "subscription_plans",
                "ordering": ["sort_order", "price_usd"],
            },
        ),
        migrations.RunPython(seed_plans, unseed_plans),
    ]
