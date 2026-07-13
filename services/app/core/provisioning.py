"""
Shared account-bootstrap logic used by both registration and OAuth sign-in,
per IMPLEMENTATION_PLAN.md Milestone 1 Epic 1.2.
"""

from core.models import User, Workspace, WorkspaceMember


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
