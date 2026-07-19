"""Backfills manifest["declared_tools"] on the first-party seeded packs so
marketplace cards can show what each pack can touch. Tool names reference
the built-in Tool catalog (0004/0012 seeds); unknown names simply render as
neutral chips in the UI.
"""

from django.db import migrations

DECLARED_TOOLS_BY_LISTING_NAME = {
    "Developer Team": ["web_search", "execute_code", "create_github_issue"],
    "Research Team": ["web_search"],
    "Marketing Team": ["web_search", "send_email", "send_slack_message"],
}


def set_declared_tools(apps, schema_editor):
    Version = apps.get_model("core", "MarketplaceListingVersion")
    for version in Version.objects.filter(
        listing__name__in=DECLARED_TOOLS_BY_LISTING_NAME
    ).select_related("listing"):
        declared = DECLARED_TOOLS_BY_LISTING_NAME[version.listing.name]
        if version.manifest.get("declared_tools") != declared:
            version.manifest["declared_tools"] = declared
            version.save(update_fields=["manifest"])


def unset_declared_tools(apps, schema_editor):
    Version = apps.get_model("core", "MarketplaceListingVersion")
    for version in Version.objects.filter(listing__name__in=DECLARED_TOOLS_BY_LISTING_NAME):
        if version.manifest.get("declared_tools"):
            version.manifest["declared_tools"] = []
            version.save(update_fields=["manifest"])


class Migration(migrations.Migration):
    dependencies = [("core", "0020_approvalpolicy")]
    operations = [migrations.RunPython(set_declared_tools, unset_declared_tools)]
