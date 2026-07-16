"""
Give every coworker-less workspace a default "Assistant".

The signup flow seeds one for new personal workspaces, but accounts created
before that shipped — and organizations created empty — start with none, so
their home composer dead-ends at "create a coworker". This backfills them.

Idempotent: only touches workspaces that currently have zero coworkers.

    python manage.py backfill_default_coworkers [--dry-run]
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from core.coworkers import create_coworker
from core.models import Coworker, Workspace
from core.provisioning import (
    DEFAULT_COWORKER_NAME,
    DEFAULT_COWORKER_ROLE,
    DEFAULT_MODEL_BINDING,
)


class Command(BaseCommand):
    help = "Seed a default coworker into any workspace that has none."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List the workspaces that would be seeded without changing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        empty = (
            Workspace.objects.exclude(coworkers__isnull=False)
            .select_related("owner")
            .distinct()
        )
        seeded = 0
        for workspace in empty:
            # A workspace's owner is the natural coworker owner/creator. Skip
            # the rare orphan with no owner rather than guessing.
            if workspace.owner_id is None:
                continue
            if dry_run:
                self.stdout.write(f"would seed: {workspace.name} ({workspace.id})")
                seeded += 1
                continue
            with transaction.atomic():
                # Re-check inside the transaction to stay safe under races.
                if Coworker.objects.filter(workspace=workspace).exists():
                    continue
                create_coworker(
                    workspace=workspace,
                    owner=workspace.owner,
                    owner_type=Coworker.OwnerType.USER,
                    name=DEFAULT_COWORKER_NAME,
                    role_description=DEFAULT_COWORKER_ROLE,
                    model_binding=dict(DEFAULT_MODEL_BINDING),
                    created_by=workspace.owner,
                )
            seeded += 1
            self.stdout.write(f"seeded: {workspace.name} ({workspace.id})")

        verb = "would seed" if dry_run else "seeded"
        self.stdout.write(self.style.SUCCESS(f"Done — {verb} {seeded} workspace(s)."))
