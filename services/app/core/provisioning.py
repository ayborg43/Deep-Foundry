"""
Shared account-bootstrap logic used by both registration and OAuth sign-in,
per IMPLEMENTATION_PLAN.md Milestone 1 Epic 1.2.
"""

from django.db import transaction

from core.coworkers import create_coworker
from core.models import Coworker, User, Workspace, WorkspaceMember

# Every new workspace gets one ready-to-use coworker so a first-time user can
# start working immediately instead of being sent through the create-coworker
# form before they've seen a single result. It's an ordinary coworker —
# renameable, re-role-able, and tool-attachable like any other.
DEFAULT_COWORKER_NAME = "Assistant"
DEFAULT_COWORKER_ROLE = (
    "You are a helpful, general-purpose coworker. You can research, draft, "
    "summarize, analyze, and use the tools attached to you to get work done. "
    "Ask for clarification when a request is ambiguous, and keep answers concise. "
    "Rename or re-role me any time to make me a specialist."
)
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
    create_coworker(
        workspace=workspace,
        owner=user,
        owner_type=Coworker.OwnerType.USER,
        name=DEFAULT_COWORKER_NAME,
        role_description=DEFAULT_COWORKER_ROLE,
        model_binding=DEFAULT_MODEL_BINDING,
        created_by=user,
    )
    return workspace
