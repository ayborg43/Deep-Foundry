"""
Core <-> AI internal module interface, per API.md §12 and ARCHITECTURE.md §3.1.

This is the one seam AI modules and the Celery worker are allowed to cross to
reach Core data — never a direct import of core.models internals, never a
network call for MVP (ARCHITECTURE.md ADR-006). Functions here graduate from
stub to real implementation as the models behind them land in later
milestones; the signatures are the actual contract and shouldn't need to
change shape when that happens (get_provider_credential graduated in
Milestone 2, now that ProviderCredential exists from Milestone 1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from core.encryption import decrypt_from_bytes
from core.models import ProviderCredential


@dataclass(frozen=True)
class ResolvedCoworkerConfig:
    coworker_id: UUID | str
    role_description: str
    model_binding: dict[str, Any]
    permission_profile: dict[str, str]


@dataclass(frozen=True)
class DecryptedCredential:
    workspace_id: UUID | str
    deployment_mode: str
    api_key: str | None
    endpoint_url: str | None


@dataclass(frozen=True)
class ApprovalRequest:
    coworker_id: UUID | str
    tool_id: UUID | str
    requested_action: dict[str, Any]
    status: str = "pending"


def get_coworker_config(coworker_id: UUID | str) -> ResolvedCoworkerConfig:
    """Stub — Coworker/permission-profile models land in Milestone 3/`SECURITY.md` §3."""
    return ResolvedCoworkerConfig(
        coworker_id=coworker_id,
        role_description="(stub) Milestone 0 fixture coworker",
        model_binding={"primary": "deepseek/deepseek-v3", "fallback": ["deepseek/deepseek-r1"]},
        permission_profile={"safe": "auto", "sensitive": "approval", "dangerous": "approval"},
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


def report_task_status(task_id: UUID | str, status: str) -> None:
    """Stub — Task model lands in Milestone 6 Epic 6.1. No-op for Milestone 0."""
    return None


def create_approval_request(
    coworker_id: UUID | str, tool_id: UUID | str, requested_action: dict[str, Any]
) -> ApprovalRequest:
    """Stub — ApprovalRequest model + real approval-gate enforcement land in Milestone 4."""
    return ApprovalRequest(
        coworker_id=coworker_id, tool_id=tool_id, requested_action=requested_action
    )


def write_audit_log(
    actor_type: str,
    actor_id: UUID | str,
    action: str,
    resource_type: str,
    resource_id: UUID | str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Stub — audit_log table lands in Milestone 7 Epic 7.1. No-op for Milestone 0."""
    metadata = metadata or {}
    return None
