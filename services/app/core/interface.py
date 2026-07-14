"""
Core <-> AI internal module interface, per API.md §12 and ARCHITECTURE.md §3.1.

This is the one seam AI modules and the Celery worker are allowed to cross to
reach Core data — never a direct import of core.models internals, never a
network call for MVP (ARCHITECTURE.md ADR-006). The signatures are the stable
contract across Core, AI, and worker entrypoints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from core.encryption import decrypt_from_bytes
from core.models import ApprovalRequest as ApprovalRequestModel
from core.models import (
    AuditLog,
    Coworker,
    CoworkerToolAttachment,
    Notification,
    OrgPolicyFloor,
    ProviderCredential,
    Task,
    Tool,
    WorkspaceMember,
)


@dataclass(frozen=True)
class ResolvedCoworkerConfig:
    coworker_id: UUID | str
    role_description: str
    model_binding: dict[str, Any]
    permission_profile: dict[str, str]
    org_policy_floor: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DecryptedCredential:
    workspace_id: UUID | str
    deployment_mode: str
    api_key: str | None
    endpoint_url: str | None


@dataclass(frozen=True)
class ApprovalRequest:
    id: UUID | str
    coworker_id: UUID | str
    tool_id: UUID | str
    requested_action: dict[str, Any]
    status: str


@dataclass(frozen=True)
class ApprovalDecision:
    id: UUID | str
    coworker_id: UUID | str
    tool_id: UUID | str
    requested_action: dict[str, Any]
    status: str
    conversation_id: UUID | str | None
    message_id: UUID | str | None
    task_id: UUID | str | None
    workflow_run_step_id: UUID | str | None = None


@dataclass(frozen=True)
class ToolInfo:
    id: UUID | str
    name: str
    description: str
    input_schema: dict[str, Any]
    risk_classification: str


@dataclass(frozen=True)
class TaskRecord:
    id: UUID | str
    workspace_id: UUID | str
    coworker_id: UUID | str
    title: str
    description: str
    status: str
    execution_state: dict[str, Any]


class CoworkerNotFoundError(LookupError):
    """No Coworker with this id exists, or it has no current_version set."""


def get_coworker_config(coworker_id: UUID | str) -> ResolvedCoworkerConfig:
    """Graduated in Milestone 4 now that Coworker/CoworkerVersion/PermissionProfile
    exist (Milestone 3). Resolves against the coworker's *current* version —
    callers that need a pinned historical version go through core.coworkers directly."""
    try:
        coworker = Coworker.objects.select_related(
            "current_version", "current_version__permission_profile"
        ).get(id=coworker_id)
    except Coworker.DoesNotExist as exc:
        raise CoworkerNotFoundError(f"No coworker {coworker_id}.") from exc
    version = coworker.current_version
    if version is None:
        raise CoworkerNotFoundError(f"Coworker {coworker_id} has no current_version.")
    skill_instructions = list(
        coworker.skill_attachments.filter(enabled=True)
        .select_related("skill")
        .values_list("skill__instruction_content", flat=True)
    )
    role_description = version.role_description
    if skill_instructions:
        role_description += "\n\nInstalled skills:\n" + "\n\n".join(skill_instructions)
    org_floor = {
        row.tool_risk_classification: row.min_required_policy
        for row in OrgPolicyFloor.objects.filter(workspace=coworker.workspace, enforced=True)
    }
    return ResolvedCoworkerConfig(
        coworker_id=coworker_id,
        role_description=role_description,
        model_binding=version.model_binding,
        permission_profile=version.permission_profile.default_tool_risk_policy,
        org_policy_floor=org_floor,
    )


def get_attached_tools(coworker_id: UUID | str) -> list[ToolInfo]:
    """Enabled tool attachments for a coworker, per DATABASE.md §2.3
    coworker_tool_attachments — resolved here so callers never import
    core.models.Tool/CoworkerToolAttachment directly."""
    attachments = CoworkerToolAttachment.objects.filter(
        coworker_id=coworker_id, enabled=True
    ).select_related("tool")
    return [
        ToolInfo(
            id=a.tool.id,
            name=a.tool.name,
            description=a.tool.description,
            input_schema=a.tool.input_schema,
            risk_classification=a.tool.risk_classification,
        )
        for a in attachments
    ]


def get_tool_by_name(name: str) -> ToolInfo | None:
    tool = Tool.objects.filter(name=name).first()
    if tool is None:
        return None
    return ToolInfo(
        id=tool.id,
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_schema,
        risk_classification=tool.risk_classification,
    )


class CredentialNotFoundError(LookupError):
    """No ProviderCredential of the requested deployment_mode exists for this
    workspace. Callers (the Model Router) decide how to surface this — e.g.
    a 424/400 to the caller, not a 500."""


def get_provider_credential(workspace_id: UUID | str, deployment_mode: str) -> DecryptedCredential:
    credential = (
        ProviderCredential.objects.filter(
            workspace_id=workspace_id, deployment_mode=deployment_mode
        )
        .order_by("-is_default", "-created_at")
        .first()
    )
    if credential is None:
        raise CredentialNotFoundError(
            f"No {deployment_mode} credential configured for workspace {workspace_id}."
        )
    api_key = (
        decrypt_from_bytes(bytes(credential.encrypted_key)) if credential.encrypted_key else None
    )
    return DecryptedCredential(
        workspace_id=workspace_id,
        deployment_mode=deployment_mode,
        api_key=api_key,
        endpoint_url=credential.endpoint_url,
    )


def get_task_record(task_id: UUID | str) -> TaskRecord:
    row = Task.objects.get(id=task_id)
    return TaskRecord(
        id=row.id,
        workspace_id=row.workspace_id,
        coworker_id=row.coworker_id,
        title=row.title,
        description=row.description,
        status=row.status,
        execution_state=row.execution_state,
    )


def claim_task_execution(task_id: UUID | str) -> TaskRecord | None:
    """Claims pending/resuming work; duplicate Celery deliveries are no-ops."""
    with transaction.atomic():
        row = Task.objects.select_for_update().get(id=task_id)
        if row.status not in (Task.Status.PENDING, Task.Status.NEEDS_APPROVAL):
            return None
        row.status = Task.Status.IN_PROGRESS
        row.error_message = ""
        row.save(update_fields=["status", "error_message", "updated_at"])
    return get_task_record(task_id)


def report_task_status(
    task_id: UUID | str,
    status: str,
    *,
    execution_state: dict[str, Any] | None = None,
    result: str | None = None,
    error_message: str | None = None,
) -> None:
    updates: dict[str, Any] = {"status": status, "updated_at": timezone.now()}
    if execution_state is not None:
        updates["execution_state"] = execution_state
    if result is not None:
        updates["result"] = result
    if error_message is not None:
        updates["error_message"] = error_message
    if status in (Task.Status.COMPLETED, Task.Status.FAILED, Task.Status.BLOCKED):
        updates["completed_at"] = timezone.now()
    Task.objects.filter(id=task_id).update(**updates)


def notify_workspace(
    *, workspace_id: UUID | str, notification_type: str, payload: dict[str, Any]
) -> list[UUID | str]:
    rows = [
        Notification(
            workspace_id=workspace_id,
            user_id=user_id,
            type=notification_type,
            payload=payload,
        )
        for user_id in WorkspaceMember.objects.filter(workspace_id=workspace_id).values_list(
            "user_id", flat=True
        )
    ]
    created = Notification.objects.bulk_create(rows)
    from worker.tasks import dispatch_notification_email

    for row in created:
        try:
            dispatch_notification_email.delay(str(row.id))
        except Exception:
            # The durable in-app row is primary. A broker outage must not
            # turn a completed coworker task back into a failed task.
            continue
    return [row.id for row in created]


def get_enabled_integration(*, workspace_id: UUID | str, kind: str) -> dict[str, Any] | None:
    """Return one integration's runtime config without exposing ORM models to AI."""
    from core.encryption import decrypt_from_bytes
    from core.models import Integration

    row = Integration.objects.filter(workspace_id=workspace_id, kind=kind, enabled=True).first()
    if row is None:
        return None
    return {
        "config": row.config,
        "secret": decrypt_from_bytes(bytes(row.encrypted_secret)) if row.encrypted_secret else "",
    }


def resolve_org_action_policy(
    *, workspace_id: UUID | str, resource_type: str, action: str, context: dict[str, Any]
) -> str:
    """Evaluate Phase 3 rules without exposing Core ORM models across the seam."""
    from core.models import OrganizationPolicyRule

    rules = OrganizationPolicyRule.objects.filter(
        workspace_id=workspace_id, enabled=True,
        resource_type__in=[resource_type, "*"], action__in=[action, "*"],
    ).order_by("priority", "created_at")
    for rule in rules:
        if all(context.get(key) == value for key, value in rule.conditions.items()):
            return rule.effect
    return "allow"


def create_workspace_artifact(
    *, workspace_id: UUID | str, artifact_type: str, name: str,
    content: dict[str, Any], coworker_id: UUID | str | None = None,
) -> dict[str, str]:
    """Persist model-generated structured output behind the Core interface."""
    import hashlib
    import json
    from core.models import Artifact

    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    row = Artifact.objects.create(
        workspace_id=workspace_id, artifact_type=artifact_type, name=name,
        content=content, checksum=hashlib.sha256(canonical.encode()).hexdigest(),
        source_coworker_id=coworker_id,
    )
    return {"artifact_id": str(row.id), "checksum": row.checksum}


def create_approval_request(
    coworker_id: UUID | str,
    tool_id: UUID | str,
    requested_action: dict[str, Any],
    *,
    conversation_id: UUID | str | None = None,
    message_id: UUID | str | None = None,
    task_id: UUID | str | None = None,
    workflow_run_step_id: UUID | str | None = None,
) -> ApprovalRequest:
    """Persists a pending approval_requests row, per DATABASE.md §2.3.

    Exactly one of task_id/workflow_run_step_id/message_id must identify
    what's blocked on this decision — enforced here rather than trusted from
    the caller, since a caller bug here would mean an approval request that
    can never be resolved from any UI. `conversation_id` is extra context
    that may accompany `message_id`, not itself a trigger."""
    triggers = [task_id, workflow_run_step_id, message_id]
    if sum(trigger is not None for trigger in triggers) != 1:
        raise ValueError(
            "create_approval_request requires exactly one of "
            "task_id/workflow_run_step_id/message_id."
        )
    row = ApprovalRequestModel.objects.create(
        task_id=task_id,
        workflow_run_step_id=workflow_run_step_id,
        conversation_id=conversation_id,
        message_id=message_id,
        coworker_id=coworker_id,
        tool_id=tool_id,
        requested_action=requested_action,
    )
    return ApprovalRequest(
        id=row.id,
        coworker_id=coworker_id,
        tool_id=tool_id,
        requested_action=requested_action,
        status=row.status,
    )


class ApprovalRequestNotFoundError(LookupError):
    """No ApprovalRequest with this id exists."""


class ApprovalRequestAlreadyDecidedError(ValueError):
    """The approval request is no longer pending (already approved/denied/expired)."""


def _to_approval_decision(row: ApprovalRequestModel) -> ApprovalDecision:
    return ApprovalDecision(
        id=row.id,
        coworker_id=row.coworker_id,
        tool_id=row.tool_id,
        requested_action=row.requested_action,
        status=row.status,
        conversation_id=row.conversation_id,
        message_id=row.message_id,
        task_id=row.task_id,
        workflow_run_step_id=row.workflow_run_step_id,
    )


def get_approval_request_for_tool_call(
    message_id: UUID | str, tool_call_id: str
) -> ApprovalDecision | None:
    """Looks up whether a specific tool call within a message already has an
    approval_requests row (pending or decided) — the chat orchestrator's
    idempotency check for "have we seen this tool call before"."""
    row = (
        ApprovalRequestModel.objects.filter(
            message_id=message_id, requested_action__tool_call_id=tool_call_id
        )
        .order_by("-created_at")
        .first()
    )
    return _to_approval_decision(row) if row is not None else None


def get_approval_request_for_task_call(
    task_id: UUID | str, tool_call_id: str
) -> ApprovalDecision | None:
    row = (
        ApprovalRequestModel.objects.filter(
            task_id=task_id, requested_action__tool_call_id=tool_call_id
        )
        .order_by("-created_at")
        .first()
    )
    return _to_approval_decision(row) if row is not None else None


def get_approval_request_for_workflow_step(
    workflow_run_step_id: UUID | str,
) -> ApprovalDecision | None:
    row = (
        ApprovalRequestModel.objects.filter(workflow_run_step_id=workflow_run_step_id)
        .order_by("-created_at")
        .first()
    )
    return _to_approval_decision(row) if row is not None else None


def get_approval_request(approval_request_id: UUID | str) -> ApprovalDecision:
    try:
        row = ApprovalRequestModel.objects.get(id=approval_request_id)
    except ApprovalRequestModel.DoesNotExist as exc:
        raise ApprovalRequestNotFoundError(f"No approval request {approval_request_id}.") from exc
    return _to_approval_decision(row)


def decide_approval_request(
    approval_request_id: UUID | str, *, approve: bool, decided_by_user_id: UUID | str
) -> ApprovalDecision:
    """Atomically transitions a pending approval_requests row to
    approved/denied. `select_for_update` so two concurrent decisions on the
    same request can't both succeed — SECURITY.md §4's "every approval
    decision is attributed" guarantee would be meaningless if a race let a
    dangerous action execute after having been denied."""
    with transaction.atomic():
        row = ApprovalRequestModel.objects.select_for_update().get(id=approval_request_id)
        if row.status != ApprovalRequestModel.Status.PENDING:
            raise ApprovalRequestAlreadyDecidedError(
                f"Approval request {approval_request_id} is already {row.status}."
            )
        row.status = (
            ApprovalRequestModel.Status.APPROVED if approve else ApprovalRequestModel.Status.DENIED
        )
        row.decided_by_id = decided_by_user_id
        row.decided_at = timezone.now()
        row.save(update_fields=["status", "decided_by", "decided_at"])
    return _to_approval_decision(row)


def write_audit_log(
    actor_type: str,
    actor_id: UUID | str | None,
    action: str,
    resource_type: str,
    resource_id: UUID | str | None,
    metadata: dict[str, Any] | None = None,
    *,
    workspace_id: UUID | str | None = None,
) -> AuditLog:
    """Persists an append-only audit_log row, per DATABASE.md §2.3 /
    SECURITY.md §4. No update/delete path exists anywhere for this model —
    callers that need to correct a row write a new one."""
    return AuditLog.objects.create(
        workspace_id=workspace_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata or {},
    )
