from django.db import migrations

# Removes the first-party demo capability packs seeded by
# 0011_seed_v2_capability_packs (Developer/Marketing/Research Team) together
# with their placeholder publisher workspace and user. The marketplace starts
# empty; anything real that users published is untouched. Coworkers already
# provisioned from these packs are ordinary workspace coworkers and are kept —
# only the install records (PROTECTed against listing deletion) are dropped.


def remove_demo_packs(apps, schema_editor):
    User = apps.get_model("core", "User")
    Workspace = apps.get_model("core", "Workspace")
    Listing = apps.get_model("core", "MarketplaceListing")
    Install = apps.get_model("core", "MarketplaceInstall")

    user = User.objects.filter(email="marketplace@agentarium.local").first()
    if user is None:
        return
    workspaces = Workspace.objects.filter(owner=user, name="Deep-Foundry First Party")
    listings = Listing.objects.filter(publisher_workspace__in=workspaces)
    Install.objects.filter(listing_version__listing__in=listings).delete()
    listings.delete()
    workspaces.delete()
    user.delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0024_seed_post_tweet_tool")]
    operations = [migrations.RunPython(remove_demo_packs, migrations.RunPython.noop)]
