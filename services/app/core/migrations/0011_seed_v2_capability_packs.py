from django.db import migrations
from django.utils import timezone


PACKS = [
    {
        "name": "Developer Team",
        "summary": "A manager, developer, and tester with a scheduled delivery workflow.",
        "coworkers": [
            {"key": "manager", "name": "Engineering Manager", "team_role": "manager", "role_description": "Plan engineering work, delegate clearly, and synthesize production-ready results."},
            {"key": "developer", "name": "Software Developer", "team_role": "developer", "role_description": "Implement maintainable software with concise explanations and secure defaults."},
            {"key": "tester", "name": "QA Engineer", "team_role": "tester", "role_description": "Design and execute tests, identify regressions, and report reproducible evidence."},
        ],
        "workflows": [{
            "name": "Weekly engineering review",
            "schedule_cron": "0 9 * * 1",
            "steps": [
                {"type": "coworker_action", "coworker_ref": "developer", "title": "Prepare engineering update", "objective": "Review current engineering work and prepare a concise progress update."},
                {"type": "coworker_action", "coworker_ref": "tester", "title": "Validate engineering update", "objective": "Review recent work for test gaps and risks."},
                {"type": "human_checkpoint", "title": "Approve weekly engineering report"},
                {"type": "coworker_action", "coworker_ref": "manager", "title": "Publish final engineering report", "objective": "Synthesize the approved weekly engineering report."},
            ],
        }],
    },
    {
        "name": "Marketing Team",
        "summary": "Campaign planning, content creation, and human approval before publishing.",
        "coworkers": [
            {"key": "manager", "name": "Marketing Lead", "team_role": "manager", "role_description": "Set campaign strategy and synthesize channel-specific plans."},
            {"key": "writer", "name": "Content Writer", "team_role": "writer", "role_description": "Write clear, audience-aware campaign content."},
            {"key": "reviewer", "name": "Brand Reviewer", "team_role": "reviewer", "role_description": "Review content for accuracy, tone, brand fit, and avoid unsupported claims."},
        ],
        "workflows": [{
            "name": "Weekly campaign draft",
            "schedule_cron": "0 10 * * 2",
            "steps": [
                {"type": "coworker_action", "coworker_ref": "writer", "title": "Draft campaign", "objective": "Draft this week's campaign content."},
                {"type": "coworker_action", "coworker_ref": "reviewer", "title": "Review campaign", "objective": "Review the campaign draft for brand and factual risks."},
                {"type": "human_checkpoint", "title": "Approve campaign"},
            ],
        }],
    },
    {
        "name": "Research Team",
        "summary": "A research manager, researcher, and reviewer for evidence-grounded briefs.",
        "coworkers": [
            {"key": "manager", "name": "Research Manager", "team_role": "manager", "role_description": "Scope research questions and synthesize evidence into decisions."},
            {"key": "researcher", "name": "Researcher", "team_role": "researcher", "role_description": "Find relevant evidence, preserve citations, and separate facts from inference."},
            {"key": "reviewer", "name": "Evidence Reviewer", "team_role": "reviewer", "role_description": "Challenge evidence quality, missing counterarguments, and citation accuracy."},
        ],
        "workflows": [],
    },
]


def seed_packs(apps, schema_editor):
    User = apps.get_model("core", "User")
    Workspace = apps.get_model("core", "Workspace")
    WorkspaceMember = apps.get_model("core", "WorkspaceMember")
    Listing = apps.get_model("core", "MarketplaceListing")
    Version = apps.get_model("core", "MarketplaceListingVersion")
    user, _ = User.objects.get_or_create(
        email="marketplace@agentarium.local",
        defaults={"display_name": "Agentarium", "password": "!", "is_active": False},
    )
    workspace, _ = Workspace.objects.get_or_create(
        name="Agentarium First Party",
        owner=user,
        defaults={"type": "organization", "plan_tier": "self_hosted_free"},
    )
    WorkspaceMember.objects.get_or_create(workspace=workspace, user=user, defaults={"role": "owner"})
    now = timezone.now()
    for pack in PACKS:
        listing, _ = Listing.objects.get_or_create(
            publisher_workspace=workspace,
            name=pack["name"],
            defaults={
                "listing_type": "capability_pack",
                "summary": pack["summary"],
                "visibility": "public",
                "pricing_model": "free",
                "verified_publisher": True,
            },
        )
        Version.objects.get_or_create(
            listing=listing,
            version_string="1.0.0",
            defaults={
                "manifest": {
                    "schema_version": "1",
                    "declared_tools": [],
                    "agent_team": {"name": pack["name"], "collaboration_pattern": "manager_delegate"},
                    "coworkers": pack["coworkers"],
                    "workflows": pack["workflows"],
                },
                "changelog": "First-party V2 launch pack.",
                "review_status": "approved",
                "reviewed_at": now,
                "published_at": now,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0010_workflowrun_agentteam_agentteamversion_agentteamrun_and_more")]
    operations = [migrations.RunPython(seed_packs, migrations.RunPython.noop)]
