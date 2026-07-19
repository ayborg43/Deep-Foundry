"""Backfills manifest["category"] on the first-party seeded listings so the
marketplace's job-domain filter pills have data. Publishers set `category`
in their manifest going forward; listings without one only appear under
"All". Categories: Support, Data & ops, Finance, Security, Content.
"""

from django.db import migrations

CATEGORY_BY_LISTING_NAME = {
    "Developer Team": "Data & ops",
    "Research Team": "Data & ops",
    "Marketing Team": "Content",
}


def set_categories(apps, schema_editor):
    Version = apps.get_model("core", "MarketplaceListingVersion")
    for version in Version.objects.filter(
        listing__name__in=CATEGORY_BY_LISTING_NAME
    ).select_related("listing"):
        category = CATEGORY_BY_LISTING_NAME[version.listing.name]
        if version.manifest.get("category") != category:
            version.manifest["category"] = category
            version.save(update_fields=["manifest"])


def unset_categories(apps, schema_editor):
    Version = apps.get_model("core", "MarketplaceListingVersion")
    for version in Version.objects.filter(listing__name__in=CATEGORY_BY_LISTING_NAME):
        if "category" in version.manifest:
            del version.manifest["category"]
            version.save(update_fields=["manifest"])


class Migration(migrations.Migration):
    dependencies = [("core", "0018_approvalrequest_summary_rationale")]
    operations = [migrations.RunPython(set_categories, unset_categories)]
