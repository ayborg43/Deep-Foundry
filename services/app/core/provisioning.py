"""
Shared account-bootstrap logic used by both registration and OAuth sign-in,
per IMPLEMENTATION_PLAN.md Milestone 1 Epic 1.2.

New workspaces start blank — no seeded coworker. The first coworker (or a
whole team) is created by the user: manually, from a starter template, or by
describing what they need in the Home composer, which designs and provisions
a team via ai.team_designer + core.starter_teams.
"""

from django.db import transaction

from core.models import User, Workspace, WorkspaceMember

# Sensible default model; matches the task engine's own fallback.
DEFAULT_MODEL_BINDING = {"primary": "deepseek-v4-flash"}


@transaction.atomic
def provision_personal_workspace(user: User) -> Workspace:
    workspace = Workspace.objects.create(
        name=f"{user.display_name or user.email}'s Workspace",
        type=Workspace.WorkspaceType.PERSONAL,
        owner=user,
    )
    WorkspaceMember.objects.create(
        workspace=workspace, user=user, role=WorkspaceMember.Role.OWNER
    )
    return workspace
