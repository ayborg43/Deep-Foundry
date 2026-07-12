"""
Local-dev seed data per IMPLEMENTATION_PLAN.md Milestone 0 / Epic 0.2.

Creates one dev user with a personal workspace they own, as an Owner member —
just enough fixture data for later milestones' manual testing to have
something to point at. Idempotent: safe to run more than once.
"""

from django.core.management.base import BaseCommand

from core.models import User, Workspace, WorkspaceMember


class Command(BaseCommand):
    help = "Seed a dev user + personal workspace for local development."

    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(
            email="dev@agentarium.local",
            defaults={"display_name": "Dev User"},
        )
        if created:
            user.set_password("dev-password-only")
            user.save(update_fields=["password"])
            self.stdout.write(self.style.SUCCESS(f"Created user {user.email}"))
        else:
            self.stdout.write(f"User {user.email} already exists")

        workspace, created = Workspace.objects.get_or_create(
            owner=user,
            type=Workspace.WorkspaceType.PERSONAL,
            defaults={"name": "Dev User's Workspace"},
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created workspace {workspace.name}"))
        else:
            self.stdout.write(f"Workspace {workspace.name} already exists")

        _, created = WorkspaceMember.objects.get_or_create(
            workspace=workspace, user=user, defaults={"role": WorkspaceMember.Role.OWNER}
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Added dev user as Owner of their workspace"))

        self.stdout.write(self.style.SUCCESS("Seed complete."))
