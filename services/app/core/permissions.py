from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import BasePermission

from core.models import Coworker, Tool, Workspace, WorkspaceMember


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


def get_coworker_for_member(
    user, coworker_id: str, *, require_write: bool = False
) -> Coworker:
    """Used by views scoped by coworker id directly (detail, versions,
    rollback, tool attach/detach) rather than nested under a workspace URL."""
    try:
        coworker = Coworker.objects.select_related("workspace", "current_version").get(
            id=coworker_id
        )
    except (Coworker.DoesNotExist, ValueError, TypeError) as exc:
        raise NotFound("Coworker not found.") from exc
    membership = WorkspaceMember.objects.filter(workspace=coworker.workspace, user=user).first()
    if membership is None:
        raise PermissionDenied("You are not a member of this coworker's workspace.")
    if require_write and membership.role not in (
        WorkspaceMember.Role.OWNER,
        WorkspaceMember.Role.ADMIN,
    ):
        raise PermissionDenied("Only workspace Owner/Admin can modify this coworker.")
    return coworker


def resolve_tool_permission(
    risk_classification: str,
    permission_profile: dict[str, str],
    org_policy_floor: dict[str, str] | None = None,
) -> str:
    """The Security & Permissions library's single evaluation point for
    "can this tool call auto-execute, or does it need approval?" —
    SECURITY.md §4 / SOUL.md §15.2. Called identically from Core's chat
    orchestration, the AI modules, and the Celery worker — never
    reimplemented at any call site.

    `dangerous` always requires approval: hard-coded here as a return value
    the caller-supplied `permission_profile` cannot override, even though
    PermissionProfile.save() also rejects persisting dangerous->auto. A
    single evaluation point can't rely on every write path having enforced
    the invariant — this is the backstop.
    """
    if risk_classification == Tool.RiskClassification.DANGEROUS:
        return "approval"
    if risk_classification not in (
        Tool.RiskClassification.SAFE,
        Tool.RiskClassification.SENSITIVE,
    ):
        return "approval"
    coworker_decision = permission_profile.get(risk_classification, "approval")
    org_decision = (org_policy_floor or {}).get(risk_classification, "auto")
    # Approval is the strictest decision. Invalid or missing coworker values
    # fail closed, and an org floor can raise but never lower strictness.
    if coworker_decision != "auto" or org_decision != "auto":
        return "approval"
    return "auto"
