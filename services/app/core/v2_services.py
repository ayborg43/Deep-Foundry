"""Phase 2 domain services.

Version creation, Marketplace review/install, team provisioning and workflow
startup live here so web, SDK and worker entrypoints share the same invariants.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from typing import Any

from django.db import transaction
from django.utils import timezone
from croniter import croniter
from rest_framework.exceptions import PermissionDenied, ValidationError

from core.coworkers import create_coworker
from core.interface import write_audit_log
from core.models import (
    AgentTeam,
    AgentTeamMember,
    AgentTeamRun,
    AgentTeamVersion,
    ApiToken,
    MarketplaceInstall,
    MarketplaceListing,
    MarketplaceListingVersion,
    MarketplaceReview,
    PermissionProfile,
    SkillVersion,
    Tool,
    User,
    Workflow,
    WorkflowRun,
    WorkflowRunStep,
    WorkflowTrigger,
    WorkflowVersion,
    Workspace,
    WorkspaceMember,
)


def require_workspace_admin(user: User, workspace: Workspace) -> WorkspaceMember:
    membership = WorkspaceMember.objects.filter(user=user, workspace=workspace).first()
    if membership is None or membership.role not in (
        WorkspaceMember.Role.OWNER,
        WorkspaceMember.Role.ADMIN,
    ):
        raise PermissionDenied("Workspace Owner/Admin access is required.")
    return membership


def create_agent_team(*, workspace: Workspace, user: User, payload: dict[str, Any]) -> AgentTeam:
    require_workspace_admin(user, workspace)
    members = payload.get("members") or []
    if not members:
        raise ValidationError({"members": "At least one coworker is required."})
    coworker_ids = [member.get("coworker_id") for member in members]
    coworkers = {
        str(row.id): row
        for row in workspace.coworkers.filter(id__in=coworker_ids, status="active")
    }
    if len(coworkers) != len(set(map(str, coworker_ids))):
        raise ValidationError({"members": "Every coworker must be active in the workspace."})
    pattern = payload.get("collaboration_pattern", AgentTeam.CollaborationPattern.MANAGER_DELEGATE)
    if pattern not in AgentTeam.CollaborationPattern.values:
        raise ValidationError({"collaboration_pattern": "Unsupported collaboration pattern."})
    if pattern == AgentTeam.CollaborationPattern.MANAGER_DELEGATE:
        if sum(member.get("role") == AgentTeamMember.Role.MANAGER for member in members) != 1:
            raise ValidationError({"members": "Manager/delegate teams require exactly one manager."})
    with transaction.atomic():
        team = AgentTeam.objects.create(
            workspace=workspace, name=payload.get("name", "Untitled team"), collaboration_pattern=pattern
        )
        version = AgentTeamVersion.objects.create(agent_team=team, version_number=1, created_by=user)
        for position, member in enumerate(members):
            role = member.get("role", AgentTeamMember.Role.CUSTOM)
            if role not in AgentTeamMember.Role.values:
                raise ValidationError({"members": f"Unsupported role {role!r}."})
            AgentTeamMember.objects.create(
                agent_team_version=version,
                coworker=coworkers[str(member["coworker_id"])],
                role=role,
                custom_role_label=member.get("custom_role_label", ""),
                position=position,
            )
        team.current_version = version
        team.save(update_fields=["current_version"])
    write_audit_log(
        actor_type="user", actor_id=user.id, action="agent_team.create",
        resource_type="agent_team", resource_id=team.id, workspace_id=workspace.id,
    )
    return team


def new_agent_team_version(team: AgentTeam, *, user: User, members: list[dict[str, Any]]) -> AgentTeamVersion:
    require_workspace_admin(user, team.workspace)
    if not members:
        raise ValidationError({"members": "At least one coworker is required."})
    payload = {
        "name": team.name,
        "collaboration_pattern": team.collaboration_pattern,
        "members": members,
    }
    # Reuse validation without creating a temporary team.
    coworker_ids = [member.get("coworker_id") for member in members]
    coworkers = {str(c.id): c for c in team.workspace.coworkers.filter(id__in=coworker_ids)}
    if len(coworkers) != len(set(map(str, coworker_ids))):
        raise ValidationError({"members": "Invalid workspace coworker."})
    roles = [member.get("role", AgentTeamMember.Role.CUSTOM) for member in members]
    if any(role not in AgentTeamMember.Role.values for role in roles):
        raise ValidationError({"members": "A member has an unsupported role."})
    if (
        team.collaboration_pattern == AgentTeam.CollaborationPattern.MANAGER_DELEGATE
        and roles.count(AgentTeamMember.Role.MANAGER) != 1
    ):
        raise ValidationError({"members": "Manager/delegate teams require exactly one manager."})
    with transaction.atomic():
        next_number = (team.current_version.version_number if team.current_version else 0) + 1
        version = AgentTeamVersion.objects.create(
            agent_team=team, version_number=next_number, created_by=user
        )
        for position, member in enumerate(payload["members"]):
            AgentTeamMember.objects.create(
                agent_team_version=version, coworker=coworkers[str(member["coworker_id"])],
                role=member.get("role", AgentTeamMember.Role.CUSTOM),
                custom_role_label=member.get("custom_role_label", ""), position=position,
            )
        team.current_version = version
        team.save(update_fields=["current_version"])
    return version


def start_agent_team_run(team: AgentTeam, *, user: User, objective: str) -> AgentTeamRun:
    if not objective.strip():
        raise ValidationError({"objective": "An objective is required."})
    if not WorkspaceMember.objects.filter(workspace=team.workspace, user=user).exists():
        raise PermissionDenied("You are not a member of this workspace.")
    run = AgentTeamRun.objects.create(
        agent_team=team, version=team.current_version, objective=objective, created_by=user
    )
    from worker.tasks import execute_agent_team_run

    transaction.on_commit(lambda: execute_agent_team_run.delay(str(run.id)))
    return run


def validate_workflow_definition(definition: dict[str, Any], workspace: Workspace) -> dict[str, Any]:
    steps = definition.get("steps") if isinstance(definition, dict) else None
    if not isinstance(steps, list) or not steps:
        raise ValidationError({"definition": "A workflow requires a non-empty steps array."})
    allowed = set(WorkflowRunStep.StepType.values)
    for index, step in enumerate(steps):
        if not isinstance(step, dict) or step.get("type") not in allowed:
            raise ValidationError({"definition": f"Step {index} has an unsupported type."})
        if step["type"] == WorkflowRunStep.StepType.COWORKER_ACTION:
            if not workspace.coworkers.filter(id=step.get("coworker_id"), status="active").exists():
                raise ValidationError({"definition": f"Step {index} has an invalid coworker."})
        if step["type"] == WorkflowRunStep.StepType.TOOL_CALL:
            if not step.get("coworker_id") or not Tool.objects.filter(name=step.get("tool_name")).exists():
                raise ValidationError({"definition": f"Step {index} has an invalid tool call."})
        if step["type"] == WorkflowRunStep.StepType.CONDITION:
            condition = step.get("condition")
            if not isinstance(condition, dict) or not condition.get("path") or condition.get("operator") not in ("equals", "not_equals", "exists", "contains"):
                raise ValidationError({"definition": f"Step {index} has an invalid condition."})
            for branch in ("if_true", "if_false"):
                target = step.get(branch)
                if not isinstance(target, int) or target < 0 or target > len(steps):
                    raise ValidationError({"definition": f"Step {index} has an invalid {branch} target."})
    return definition


def create_workflow(*, workspace: Workspace, user: User, name: str, definition: dict) -> Workflow:
    require_workspace_admin(user, workspace)
    definition = validate_workflow_definition(definition, workspace)
    with transaction.atomic():
        workflow = Workflow.objects.create(workspace=workspace, name=name)
        version = WorkflowVersion.objects.create(
            workflow=workflow, version_number=1, definition=definition, created_by=user
        )
        workflow.current_version = version
        workflow.save(update_fields=["current_version"])
    return workflow


def update_workflow(workflow: Workflow, *, user: User, definition: dict, name: str | None = None) -> Workflow:
    require_workspace_admin(user, workflow.workspace)
    definition = validate_workflow_definition(definition, workflow.workspace)
    with transaction.atomic():
        version = WorkflowVersion.objects.create(
            workflow=workflow,
            version_number=(workflow.current_version.version_number if workflow.current_version else 0) + 1,
            definition=definition,
            created_by=user,
        )
        workflow.current_version = version
        if name:
            workflow.name = name
        workflow.save(update_fields=["current_version", "name"])
    return workflow


def start_workflow_run(
    workflow: Workflow, *, triggered_by: str, context: dict[str, Any] | None = None
) -> WorkflowRun:
    with transaction.atomic():
        run = WorkflowRun.objects.create(
            workflow_version=workflow.current_version,
            triggered_by=triggered_by,
            context=context or {},
        )
        for index, definition in enumerate(workflow.current_version.definition["steps"]):
            WorkflowRunStep.objects.create(
                workflow_run=run,
                step_index=index,
                step_type=definition["type"],
                definition=definition,
            )
    from worker.tasks import execute_workflow_run

    transaction.on_commit(lambda: execute_workflow_run.delay(str(run.id)))
    return run


def _declared_tool_rows(declared_tools: list) -> list[Tool]:
    names = [item if isinstance(item, str) else item.get("name") for item in declared_tools]
    rows = list(Tool.objects.filter(name__in=names))
    if len(rows) != len(set(names)):
        raise ValidationError({"declared_tools": "Every declared tool must exist in the catalog."})
    return rows


def publish_listing_version(
    listing: MarketplaceListing,
    *, version_string: str,
    manifest: dict[str, Any],
    changelog: str,
    instruction_content: str = "",
) -> MarketplaceListingVersion:
    if not version_string or not isinstance(manifest, dict):
        raise ValidationError("version_string and manifest are required.")
    declared = manifest.get("declared_tools", [])
    tools = _declared_tool_rows(declared)
    # Automated manifest review: safe/sensitive declarative skills publish
    # without core-team involvement; dangerous/bundled-code listings wait for review.
    auto_approved = (
        listing.listing_type in (
            MarketplaceListing.ListingType.SKILL,
            MarketplaceListing.ListingType.CAPABILITY_PACK,
            MarketplaceListing.ListingType.WORKFLOW_TEMPLATE,
        )
        and all(tool.risk_classification != Tool.RiskClassification.DANGEROUS for tool in tools)
        and not manifest.get("bundled_code")
    )
    now = timezone.now() if auto_approved else None
    with transaction.atomic():
        version = MarketplaceListingVersion.objects.create(
            listing=listing,
            version_string=version_string,
            manifest=manifest,
            changelog=changelog,
            review_status=(
                MarketplaceListingVersion.ReviewStatus.APPROVED
                if auto_approved
                else MarketplaceListingVersion.ReviewStatus.PENDING
            ),
            reviewed_at=now,
            published_at=now,
        )
        if listing.listing_type == MarketplaceListing.ListingType.SKILL:
            if not instruction_content.strip():
                raise ValidationError({"instruction_content": "Skill instructions are required."})
            SkillVersion.objects.create(
                listing_version=version,
                instruction_content=instruction_content,
                declared_tools=declared,
                dependencies=manifest.get("dependencies", []),
            )
    from core.v3_services import scan_listing_version

    scan_listing_version(version)
    return version


def install_listing(
    version: MarketplaceListingVersion, *, workspace: Workspace, user: User
) -> MarketplaceInstall:
    require_workspace_admin(user, workspace)
    if version.review_status != MarketplaceListingVersion.ReviewStatus.APPROVED:
        raise ValidationError("Only approved Marketplace versions can be installed.")
    manifest = version.manifest
    with transaction.atomic():
        install, _ = MarketplaceInstall.objects.get_or_create(
            workspace=workspace, listing_version=version, defaults={"installed_by": user}
        )
        # Capability Packs can provision a ready-to-run team and workflow.
        if version.listing.listing_type == MarketplaceListing.ListingType.CAPABILITY_PACK:
            created = []
            created_by_key = {}
            profile, _ = PermissionProfile.objects.get_or_create(
                workspace=workspace, name="Default"
            )
            for template in manifest.get("coworkers", []):
                coworker = create_coworker(
                    workspace=workspace,
                    owner=user,
                    name=template["name"],
                    role_description=template["role_description"],
                    model_binding=template.get(
                        "model_binding", {"primary": "deepseek-v4-flash", "fallback": []}
                    ),
                    created_by=user,
                    permission_profile=profile,
                )
                created.append((coworker, template.get("team_role", "custom")))
                created_by_key[template.get("key", template["name"])] = coworker
            if created:
                team_payload = manifest.get("agent_team", {})
                create_agent_team(
                    workspace=workspace,
                    user=user,
                    payload={
                        "name": team_payload.get("name", version.listing.name),
                        "collaboration_pattern": team_payload.get(
                            "collaboration_pattern", "manager_delegate"
                        ),
                        "members": [
                            {"coworker_id": str(coworker.id), "role": role}
                            for coworker, role in created
                        ],
                    },
                )
            for workflow_template in manifest.get("workflows", []):
                definition = {"steps": []}
                for source_step in workflow_template.get("steps", []):
                    step = dict(source_step)
                    coworker_ref = step.pop("coworker_ref", None)
                    if coworker_ref:
                        step["coworker_id"] = str(created_by_key[coworker_ref].id)
                    definition["steps"].append(step)
                workflow = create_workflow(
                    workspace=workspace,
                    user=user,
                    name=workflow_template["name"],
                    definition=definition,
                )
                schedule = workflow_template.get("schedule_cron")
                if schedule:
                    WorkflowTrigger.objects.create(
                        workflow=workflow,
                        trigger_type=WorkflowTrigger.TriggerType.SCHEDULED,
                        schedule_cron=schedule,
                        next_run_at=croniter(schedule, timezone.now()).get_next(datetime),
                        enabled=True,
                    )
    write_audit_log(
        actor_type="user", actor_id=user.id, action="marketplace.install",
        resource_type="marketplace_listing", resource_id=version.listing_id,
        workspace_id=workspace.id, metadata={"version": version.version_string},
    )
    return install


def create_api_token(*, workspace: Workspace, user: User, name: str, scopes: list[str]) -> tuple[ApiToken, str]:
    require_workspace_admin(user, workspace)
    allowed = {"read", "publish"}
    if not scopes or not set(scopes).issubset(allowed):
        raise ValidationError({"scopes": "Scopes must contain read and/or publish."})
    plaintext = "agt_" + secrets.token_urlsafe(32)
    digest = hashlib.sha256(plaintext.encode()).hexdigest()
    row = ApiToken.objects.create(
        workspace=workspace,
        user=user,
        name=name,
        token_prefix=plaintext[:12],
        token_hash=digest,
        scopes=scopes,
    )
    return row, plaintext
