from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import BasePermission

from core.models import Workspace, WorkspaceMember


class IsWorkspaceMember(BasePermission):
    """Read requires membership; write requires Owner/Admin — the only two
    roles that exist at Milestone 1 scope (single-owner personal workspaces,
    no invites yet)."""

    def has_object_permission(self, request, view, obj: Workspace) -> bool:
        membership = WorkspaceMember.objects.filter(workspace=obj, user=request.user).first()
        if membership is None:
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return membership.role in (WorkspaceMember.Role.OWNER, WorkspaceMember.Role.ADMIN)


def get_workspace_for_member(user, workspace_id: str) -> Workspace:
    """Used by views whose resource is nested under a workspace (e.g. provider
    credentials) rather than the workspace itself being the object."""
    try:
        workspace = Workspace.objects.get(id=workspace_id)
    except (Workspace.DoesNotExist, ValueError, TypeError) as exc:
        raise NotFound("Workspace not found.") from exc
    if not WorkspaceMember.objects.filter(workspace=workspace, user=user).exists():
        raise PermissionDenied("You are not a member of this workspace.")
    return workspace
