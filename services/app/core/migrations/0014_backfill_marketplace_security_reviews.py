from django.db import migrations


def backfill(apps, schema_editor):
    Version = apps.get_model("core", "MarketplaceListingVersion")
    Review = apps.get_model("core", "MarketplaceSecurityReview")
    for version in Version.objects.all():
        manifest = version.manifest or {}
        findings = []
        score = 100
        if manifest.get("bundled_code"):
            score -= 45
            findings.append({"severity": "high", "code": "bundled_code", "message": "Bundled executable code requires manual review."})
        if len(manifest.get("declared_tools", [])) > 8:
            score -= 15
            findings.append({"severity": "medium", "code": "broad_permissions", "message": "The package declares an unusually broad tool set."})
        score = max(0, score)
        Review.objects.get_or_create(
            listing_version=version,
            defaults={"score": score, "status": "passed" if score >= 80 else "needs_review", "findings": findings},
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0013_alter_teammember_role_and_more")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
