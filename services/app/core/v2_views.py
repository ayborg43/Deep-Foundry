from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime

from croniter import croniter
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.encryption import decrypt_from_bytes, encrypt_to_bytes
from core.interface import write_audit_log
from core.models import (
    AgentTeam,
    AgentTeamRun,
    ApiToken,
    Coworker,
    CoworkerSkillAttachment,
    Integration,
    MarketplaceInstall,
    MarketplaceListing,
    MarketplaceListingVersion,
    MarketplaceReview,
    OrgPolicyFloor,
    Project,
    ProjectResource,
    SkillVersion,
    Subscription,
    Team,
    TeamMember,
    Workflow,
    WorkflowRun,
    WorkflowRunStep,
    WorkflowTrigger,
    Workspace,
    WorkspaceMember,
    User,
)
from core.permissions import get_coworker_for_member, get_workspace_for_member
from core.v2_services import (
    attach_installed_skill,
    create_agent_team,
    create_api_token,
    create_workflow,
    install_listing,
    new_agent_team_version,
    publish_listing_version,
    require_workspace_admin,
    start_agent_team_run,
    start_workflow_run,
    update_workflow,
)


def _workspace_for_write(user, workspace_id) -> Workspace:
    workspace = get_workspace_for_member(user, workspace_id)
    require_workspace_admin(user, workspace)
    return workspace


def _team_data(team: AgentTeam) -> dict:
    version = team.current_version
    return {
        "id": str(team.id),
        "workspace_id": str(team.workspace_id),
        "name": team.name,
        "collaboration_pattern": team.collaboration_pattern,
        "version": version.version_number if version else None,
        "members": [
            {
                "id": str(member.id),
                "coworker_id": str(member.coworker_id),
                "coworker_name": member.coworker.name,
                "role": member.role,
                "custom_role_label": member.custom_role_label,
                "position": member.position,
            }
            for member in (version.members.select_related("coworker").all() if version else [])
        ],
    }


def _run_data(run: WorkflowRun) -> dict:
    return {
        "id": str(run.id),
        "workflow_id": str(run.workflow_version.workflow_id),
        "workflow_name": run.workflow_version.workflow.name,
        "version": run.workflow_version.version_number,
        "triggered_by": run.triggered_by,
        "status": run.status,
        "current_step_index": run.current_step_index,
        "context": run.context,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "steps": [
            {
                "id": str(step.id), "step_index": step.step_index,
                "step_type": step.step_type, "status": step.status,
                "definition": step.definition, "result": step.result,
            }
            for step in run.steps.all()
        ],
    }


def _workflow_data(workflow: Workflow) -> dict:
    return {
        "id": str(workflow.id), "workspace_id": str(workflow.workspace_id),
        "name": workflow.name,
        "version": workflow.current_version.version_number if workflow.current_version else None,
        "definition": workflow.current_version.definition if workflow.current_version else {},
        "triggers": [
            {
                "id": str(trigger.id), "trigger_type": trigger.trigger_type,
                "schedule_cron": trigger.schedule_cron, "event_source": trigger.event_source,
                "enabled": trigger.enabled, "next_run_at": trigger.next_run_at,
            }
            for trigger in workflow.triggers.all()
        ],
    }


def _listing_data(listing: MarketplaceListing, *, detail: bool = False) -> dict:
    latest = listing.versions.filter(
        review_status=MarketplaceListingVersion.ReviewStatus.APPROVED
    ).order_by("-published_at").first()
    reviews = listing.reviews.aggregate(count=Count("id"), rating=Avg("rating"))
    data = {
        "id": str(listing.id), "name": listing.name, "summary": listing.summary,
        "listing_type": listing.listing_type, "visibility": listing.visibility,
        "pricing_model": listing.pricing_model,
        "price_usd": str(listing.price_usd) if listing.price_usd is not None else None,
        "verified_publisher": listing.verified_publisher,
        "publisher_workspace_id": str(listing.publisher_workspace_id),
        "publisher_name": listing.publisher_workspace.name,
        # Job-domain category and tool scopes, declared by the publisher in
        # the manifest — null/empty for listings that predate the fields.
        # declared_tools is in the LIST payload on purpose: "every listing
        # shows what it can touch before you install".
        "category": latest.manifest.get("category") if latest else None,
        "declared_tools": latest.manifest.get("declared_tools", []) if latest else [],
        "latest_version": latest.version_string if latest else None,
        "install_count": listing.versions.aggregate(total=Count("installs"))["total"],
        "review_count": reviews["count"], "rating": reviews["rating"],
    }
    if latest and hasattr(latest, "security_review"):
        data["security_review"] = {
            "score": latest.security_review.score,
            "status": latest.security_review.status,
            "findings": latest.security_review.findings,
        }
    if detail and latest:
        data.update(
            latest_version_id=str(latest.id), manifest=latest.manifest,
            declared_tools=latest.manifest.get("declared_tools", []),
            changelog=latest.changelog,
        )
        if hasattr(latest, "skill"):
            data["instruction_content"] = latest.skill.instruction_content
    return data


class OrganizationListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        rows = Workspace.objects.filter(type=Workspace.WorkspaceType.ORGANIZATION, members__user=request.user)
        return Response([{"id": str(row.id), "name": row.name, "plan_tier": row.plan_tier} for row in rows])

    def post(self, request: Request) -> Response:
        name = str(request.data.get("name", "")).strip()
        if not name:
            raise ValidationError({"name": "Name is required."})
        plan_tier = request.data.get("plan_tier", Workspace.PlanTier.SELF_HOSTED_FREE)
        if plan_tier not in Workspace.PlanTier.values:
            raise ValidationError({"plan_tier": "Unsupported plan tier."})
        with transaction.atomic():
            workspace = Workspace.objects.create(
                name=name, type=Workspace.WorkspaceType.ORGANIZATION, owner=request.user,
                plan_tier=plan_tier,
            )
            WorkspaceMember.objects.create(
                workspace=workspace, user=request.user, role=WorkspaceMember.Role.OWNER
            )
            Subscription.objects.create(workspace=workspace, plan_tier=workspace.plan_tier)
        return Response({"id": str(workspace.id), "name": workspace.name}, status=201)


class WorkspaceMemberListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, workspace_id: str) -> Response:
        workspace = get_workspace_for_member(request.user, workspace_id)
        rows = workspace.members.select_related("user")
        return Response([
            {"id": str(row.id), "user_id": str(row.user_id), "email": row.user.email, "role": row.role}
            for row in rows
        ])

    def post(self, request: Request, workspace_id: str) -> Response:
        workspace = _workspace_for_write(request.user, workspace_id)
        email = User.objects.normalize_email(request.data.get("email", ""))
        role = request.data.get("role", WorkspaceMember.Role.MEMBER)
        if role not in WorkspaceMember.Role.values or role == WorkspaceMember.Role.OWNER:
            raise ValidationError({"role": "Invite role must be admin, member, or guest."})
        if not email:
            raise ValidationError({"email": "A valid email address is required."})
        user, created_user = User.objects.get_or_create(
            email=email, defaults={"display_name": email.split("@")[0]}
        )
        if created_user:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        member, created = WorkspaceMember.objects.update_or_create(
            workspace=workspace, user=user,
            defaults={"role": role, "invited_by": request.user},
        )
        return Response(
            {"id": str(member.id), "email": user.email, "role": member.role},
            status=201 if created else 200,
        )


class WorkspaceMemberDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, workspace_id: str, member_id: str) -> Response:
        workspace = _workspace_for_write(request.user, workspace_id)
        member = get_object_or_404(WorkspaceMember, id=member_id, workspace=workspace)
        if member.role == WorkspaceMember.Role.OWNER:
            raise ValidationError("The workspace owner role cannot be changed here.")
        role = request.data.get("role")
        if role not in (WorkspaceMember.Role.ADMIN, WorkspaceMember.Role.MEMBER, WorkspaceMember.Role.GUEST):
            raise ValidationError({"role": "Invalid role."})
        member.role = role
        member.save(update_fields=["role"])
        return Response({"id": str(member.id), "role": member.role})

    def delete(self, request: Request, workspace_id: str, member_id: str) -> Response:
        workspace = _workspace_for_write(request.user, workspace_id)
        member = get_object_or_404(WorkspaceMember, id=member_id, workspace=workspace)
        if member.role == WorkspaceMember.Role.OWNER:
            raise ValidationError("The workspace owner cannot be removed.")
        member.delete()
        return Response(status=204)


class PolicyFloorListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, workspace_id: str) -> Response:
        workspace = get_workspace_for_member(request.user, workspace_id)
        return Response([
            {"id": str(row.id), "risk": row.tool_risk_classification,
             "min_required_policy": row.min_required_policy, "enforced": row.enforced}
            for row in workspace.policy_floors.all()
        ])

    def post(self, request: Request, workspace_id: str) -> Response:
        workspace = _workspace_for_write(request.user, workspace_id)
        risk = request.data.get("tool_risk_classification")
        if risk not in ("safe", "sensitive", "dangerous"):
            raise ValidationError({"tool_risk_classification": "Invalid risk class."})
        row, _ = OrgPolicyFloor.objects.update_or_create(
            workspace=workspace, tool_risk_classification=risk,
            defaults={"min_required_policy": "approval", "enforced": request.data.get("enforced", True)},
        )
        return Response({"id": str(row.id), "risk": risk, "min_required_policy": "approval"})


class HumanTeamListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        workspace = get_workspace_for_member(request.user, request.query_params.get("workspace_id"))
        return Response([{"id": str(t.id), "name": t.name, "member_count": t.members.count()} for t in workspace.human_teams.all()])

    def post(self, request: Request) -> Response:
        workspace = _workspace_for_write(request.user, request.data.get("workspace_id"))
        team = Team.objects.create(workspace=workspace, name=request.data.get("name", "Team"))
        for member_id in request.data.get("member_ids", []):
            membership = get_object_or_404(WorkspaceMember, id=member_id, workspace=workspace)
            TeamMember.objects.create(team=team, user=membership.user, role=membership.role)
        return Response({"id": str(team.id), "name": team.name}, status=201)


class AgentTeamListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        workspace = get_workspace_for_member(request.user, request.query_params.get("workspace_id"))
        rows = workspace.agent_teams.select_related("current_version").all()
        return Response([_team_data(row) for row in rows])

    def post(self, request: Request) -> Response:
        workspace = get_workspace_for_member(request.user, request.data.get("workspace_id"))
        team = create_agent_team(workspace=workspace, user=request.user, payload=request.data)
        return Response(_team_data(team), status=201)


class AgentTeamDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request, team_id):
        team = get_object_or_404(AgentTeam.objects.select_related("current_version", "workspace"), id=team_id)
        get_workspace_for_member(request.user, team.workspace_id)
        return team

    def get(self, request, team_id):
        return Response(_team_data(self._get(request, team_id)))

    def patch(self, request, team_id):
        team = self._get(request, team_id)
        if "name" in request.data:
            team.name = request.data["name"]
        if "collaboration_pattern" in request.data:
            team.collaboration_pattern = request.data["collaboration_pattern"]
        if "members" in request.data:
            new_agent_team_version(team, user=request.user, members=request.data["members"])
        team.save(update_fields=["name", "collaboration_pattern"])
        return Response(_team_data(team))


class AgentTeamRunView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, team_id):
        team = get_object_or_404(AgentTeam, id=team_id)
        run = start_agent_team_run(team, user=request.user, objective=request.data.get("objective", ""))
        return Response({"id": str(run.id), "status": run.status, "objective": run.objective}, status=202)


class AgentTeamRunDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, run_id):
        run = get_object_or_404(AgentTeamRun.objects.select_related("agent_team__workspace"), id=run_id)
        get_workspace_for_member(request.user, run.agent_team.workspace_id)
        tasks = run.agent_team.workspace.tasks.filter(created_by_id=run.id).values(
            "id", "title", "status", "coworker_id", "result", "error_message"
        )
        return Response({"id": str(run.id), "status": run.status, "objective": run.objective, "result": run.result, "tasks": list(tasks)})


class ProjectListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        workspace = get_workspace_for_member(request.user, request.query_params.get("workspace_id"))
        return Response([{"id": str(p.id), "name": p.name, "description": p.description, "status": p.status} for p in workspace.projects.all()])

    def post(self, request):
        workspace = _workspace_for_write(request.user, request.data.get("workspace_id"))
        project = Project.objects.create(workspace=workspace, name=request.data.get("name", "Project"), description=request.data.get("description", ""))
        return Response({"id": str(project.id), "name": project.name}, status=201)


class ProjectDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)
        get_workspace_for_member(request.user, project.workspace_id)
        return Response({"id": str(project.id), "name": project.name, "description": project.description, "status": project.status,
                         "resources": list(project.resources.values("resource_type", "resource_id"))})


class ProjectResourceCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)
        _workspace_for_write(request.user, project.workspace_id)
        resource, _ = ProjectResource.objects.get_or_create(
            project=project, resource_type=request.data.get("resource_type"), resource_id=request.data.get("resource_id")
        )
        return Response({"id": str(resource.id)}, status=201)


class WorkflowListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        workspace = get_workspace_for_member(request.user, request.query_params.get("workspace_id"))
        return Response([_workflow_data(row) for row in workspace.workflows.select_related("current_version").all()])

    def post(self, request):
        workspace = get_workspace_for_member(request.user, request.data.get("workspace_id"))
        workflow = create_workflow(workspace=workspace, user=request.user, name=request.data.get("name", "Workflow"), definition=request.data.get("definition", {}))
        return Response(_workflow_data(workflow), status=201)


class WorkflowDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request, workflow_id):
        workflow = get_object_or_404(Workflow.objects.select_related("workspace", "current_version"), id=workflow_id)
        get_workspace_for_member(request.user, workflow.workspace_id)
        return workflow

    def get(self, request, workflow_id):
        return Response(_workflow_data(self._get(request, workflow_id)))

    def patch(self, request, workflow_id):
        workflow = self._get(request, workflow_id)
        update_workflow(workflow, user=request.user, definition=request.data.get("definition", workflow.current_version.definition), name=request.data.get("name"))
        return Response(_workflow_data(workflow))


class WorkflowTriggerCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, workflow_id):
        workflow = get_object_or_404(Workflow, id=workflow_id)
        _workspace_for_write(request.user, workflow.workspace_id)
        trigger_type = request.data.get("trigger_type")
        if trigger_type not in WorkflowTrigger.TriggerType.values:
            raise ValidationError({"trigger_type": "Invalid trigger type."})
        cron = request.data.get("schedule_cron")
        next_run = None
        if trigger_type == WorkflowTrigger.TriggerType.SCHEDULED:
            if not cron or not croniter.is_valid(cron):
                raise ValidationError({"schedule_cron": "A valid cron expression is required."})
            next_run = croniter(cron, timezone.now()).get_next(datetime)
        trigger = WorkflowTrigger.objects.create(
            workflow=workflow, trigger_type=trigger_type, schedule_cron=cron,
            event_source=request.data.get("event_source"), enabled=request.data.get("enabled", True),
            next_run_at=next_run,
        )
        return Response({"id": str(trigger.id), "next_run_at": trigger.next_run_at}, status=201)


class WorkflowRunCreateListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workflow_id):
        workflow = get_object_or_404(Workflow, id=workflow_id)
        get_workspace_for_member(request.user, workflow.workspace_id)
        return Response([_run_data(row) for row in WorkflowRun.objects.filter(workflow_version__workflow=workflow).prefetch_related("steps")])

    def post(self, request, workflow_id):
        workflow = get_object_or_404(Workflow, id=workflow_id)
        get_workspace_for_member(request.user, workflow.workspace_id)
        run = start_workflow_run(workflow, triggered_by=WorkflowRun.TriggeredBy.USER, context=request.data.get("context"))
        return Response(_run_data(run), status=202)


class WorkflowRunDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, run_id):
        run = get_object_or_404(WorkflowRun.objects.select_related("workflow_version__workflow__workspace").prefetch_related("steps"), id=run_id)
        get_workspace_for_member(request.user, run.workflow_version.workflow.workspace_id)
        return Response(_run_data(run))


class WorkflowCheckpointDecisionView(APIView):
    permission_classes = [IsAuthenticated]
    approve = True

    def post(self, request, run_id, step_id):
        run = get_object_or_404(WorkflowRun.objects.select_related("workflow_version__workflow__workspace"), id=run_id)
        _workspace_for_write(request.user, run.workflow_version.workflow.workspace_id)
        step = get_object_or_404(WorkflowRunStep, id=step_id, workflow_run=run, step_type=WorkflowRunStep.StepType.HUMAN_CHECKPOINT, status=WorkflowRunStep.Status.NEEDS_APPROVAL)
        step.status = WorkflowRunStep.Status.COMPLETED if self.approve else WorkflowRunStep.Status.FAILED
        step.result = {"approved": self.approve, "comment": request.data.get("comment", "")}
        step.decided_by = request.user
        step.completed_at = timezone.now()
        step.save(update_fields=["status", "result", "decided_by", "completed_at"])
        if not self.approve:
            run.status = WorkflowRun.Status.FAILED
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "completed_at"])
        else:
            run.status = WorkflowRun.Status.RUNNING
            run.current_step_index += 1
            run.save(update_fields=["status", "current_step_index"])
            from worker.tasks import execute_workflow_run
            execute_workflow_run.delay(str(run.id))
        return Response(_run_data(run))


class WorkflowCheckpointApproveView(WorkflowCheckpointDecisionView):
    approve = True


class WorkflowCheckpointDenyView(WorkflowCheckpointDecisionView):
    approve = False


class MarketplaceListingListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = MarketplaceListing.objects.filter(
            visibility=MarketplaceListing.Visibility.PUBLIC,
            versions__review_status=MarketplaceListingVersion.ReviewStatus.APPROVED,
        ).select_related("publisher_workspace").distinct()
        if request.query_params.get("type"):
            rows = rows.filter(listing_type=request.query_params["type"])
        if request.query_params.get("query"):
            query = request.query_params["query"]
            rows = rows.filter(Q(name__icontains=query) | Q(summary__icontains=query))
        return Response([_listing_data(row) for row in rows])

    def post(self, request):
        workspace = _workspace_for_write(request.user, request.data.get("publisher_workspace_id"))
        if isinstance(request.auth, ApiToken) and "publish" not in request.auth.scopes:
            raise PermissionDenied("This API token lacks the publish scope.")
        listing = MarketplaceListing.objects.create(
            publisher_workspace=workspace, listing_type=request.data.get("listing_type"),
            name=request.data.get("name"), summary=request.data.get("summary", ""),
            visibility=request.data.get("visibility", MarketplaceListing.Visibility.PUBLIC),
            pricing_model=request.data.get("pricing_model", MarketplaceListing.PricingModel.FREE),
            price_usd=request.data.get("price_usd"),
        )
        return Response(_listing_data(listing), status=201)


class MarketplaceListingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, listing_id):
        return Response(_listing_data(get_object_or_404(MarketplaceListing, id=listing_id), detail=True))


class MarketplaceListingVersionCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, listing_id):
        listing = get_object_or_404(MarketplaceListing, id=listing_id)
        require_workspace_admin(request.user, listing.publisher_workspace)
        if isinstance(request.auth, ApiToken) and "publish" not in request.auth.scopes:
            raise PermissionDenied("This API token lacks the publish scope.")
        version = publish_listing_version(
            listing, version_string=request.data.get("version_string"),
            manifest=request.data.get("manifest", {}), changelog=request.data.get("changelog", ""),
            instruction_content=request.data.get("instruction_content", ""),
        )
        return Response({"id": str(version.id), "review_status": version.review_status, "published_at": version.published_at}, status=201)


class MarketplaceInstallView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, listing_id):
        listing = get_object_or_404(MarketplaceListing, id=listing_id)
        version_id = request.data.get("version_id")
        version = get_object_or_404(
            listing.versions,
            id=version_id,
        ) if version_id else listing.versions.filter(review_status="approved").order_by("-published_at").first()
        if version is None:
            raise ValidationError("No approved version is available.")
        workspace = get_workspace_for_member(request.user, request.data.get("workspace_id"))
        coworker = None
        if request.data.get("coworker_id"):
            coworker = get_coworker_for_member(
                request.user,
                request.data["coworker_id"],
                require_write=True,
            )
            if coworker.workspace_id != workspace.id:
                raise ValidationError("The selected coworker is not in the installation workspace.")
        if listing.pricing_model != MarketplaceListing.PricingModel.FREE:
            from core.models import MarketplaceOrder

            if not MarketplaceOrder.objects.filter(
                workspace=workspace, listing_version=version,
                status=MarketplaceOrder.Status.PAID,
            ).exists():
                return Response(
                    {"error": {"code": "payment_required", "message": "Complete Marketplace checkout before installing this paid listing.", "details": {"checkout_path": f"/marketplace/listings/{listing.id}/checkout"}}},
                    status=402,
                )
        from core.v3_services import install_dependencies

        install_dependencies(version, workspace=workspace, user=request.user)
        install = install_listing(version, workspace=workspace, user=request.user)
        skill_attachment = None
        if coworker is not None and listing.listing_type == MarketplaceListing.ListingType.SKILL:
            if not hasattr(version, "skill"):
                raise ValidationError("This Marketplace skill has no installable skill version.")
            skill_attachment = attach_installed_skill(coworker=coworker, skill=version.skill)
        return Response({
            "id": str(install.id),
            "listing_version_id": str(version.id),
            "permission_manifest": version.manifest.get("declared_tools", []),
            "coworker_id": str(coworker.id) if coworker else None,
            "skill_attachment_id": str(skill_attachment.id) if skill_attachment else None,
        }, status=201)


class MarketplaceForkView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, listing_id):
        source = get_object_or_404(MarketplaceListing, id=listing_id)
        source_version = source.versions.filter(review_status="approved").order_by("-published_at").first()
        if source_version is None:
            raise ValidationError("No approved source version exists.")
        workspace = _workspace_for_write(request.user, request.data.get("workspace_id"))
        fork = MarketplaceListing.objects.create(
            publisher_workspace=workspace, listing_type=source.listing_type,
            name=request.data.get("name", f"{source.name} (fork)"), summary=source.summary,
            visibility=MarketplaceListing.Visibility.ORG_PRIVATE,
        )
        skill_content = source_version.skill.instruction_content if hasattr(source_version, "skill") else ""
        version = publish_listing_version(
            fork, version_string="1.0.0", manifest=source_version.manifest,
            changelog=f"Forked from {source.id}@{source_version.version_string}",
            instruction_content=skill_content,
        )
        install = MarketplaceInstall.objects.create(
            workspace=workspace, listing_version=version, installed_by=request.user,
            forked_from_listing_version=source_version,
        )
        return Response({"listing_id": str(fork.id), "install_id": str(install.id)}, status=201)


class MarketplaceReviewListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, listing_id):
        listing = get_object_or_404(MarketplaceListing, id=listing_id)
        return Response([{"id": str(r.id), "rating": r.rating, "review_text": r.review_text, "user": r.user.display_name or r.user.email, "created_at": r.created_at} for r in listing.reviews.select_related("user")])

    def post(self, request, listing_id):
        listing = get_object_or_404(MarketplaceListing, id=listing_id)
        workspace = get_workspace_for_member(request.user, request.data.get("workspace_id"))
        if not MarketplaceInstall.objects.filter(workspace=workspace, listing_version__listing=listing).exists():
            raise PermissionDenied("Install the listing before reviewing it.")
        rating = int(request.data.get("rating", 0))
        if not 1 <= rating <= 5:
            raise ValidationError({"rating": "Rating must be between 1 and 5."})
        review, _ = MarketplaceReview.objects.update_or_create(
            listing=listing, workspace=workspace, user=request.user,
            defaults={"rating": rating, "review_text": request.data.get("review_text", "")},
        )
        return Response({"id": str(review.id), "rating": review.rating}, status=201)


class CoworkerSkillAttachView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, coworker_id):
        coworker = get_coworker_for_member(request.user, coworker_id, require_write=True)
        skill = get_object_or_404(SkillVersion, id=request.data.get("skill_version_id"))
        existed = CoworkerSkillAttachment.objects.filter(coworker=coworker, skill=skill).exists()
        row = attach_installed_skill(coworker=coworker, skill=skill)
        if request.data.get("enabled") is False:
            row.enabled = False
            row.save(update_fields=["enabled"])
        return Response(
            {"id": str(row.id), "skill_version_id": str(skill.id), "enabled": row.enabled},
            status=200 if existed else 201,
        )

    def delete(self, request, coworker_id, skill_id):
        coworker = get_coworker_for_member(request.user, coworker_id, require_write=True)
        get_object_or_404(CoworkerSkillAttachment, coworker=coworker, skill_id=skill_id).delete()
        return Response(status=204)


class IntegrationListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        workspace = get_workspace_for_member(request.user, request.query_params.get("workspace_id"))
        return Response([{"id": str(row.id), "kind": row.kind, "name": row.name, "config": row.config, "enabled": row.enabled, "workspace_token": row.workspace_token} for row in workspace.integrations.all()])

    def post(self, request):
        workspace = _workspace_for_write(request.user, request.data.get("workspace_id"))
        if request.data.get("kind") not in Integration.Kind.values:
            raise ValidationError({"kind": "Unsupported integration kind."})
        secret = request.data.get("secret") or secrets.token_urlsafe(32)
        integration = Integration.objects.create(
            workspace=workspace, kind=request.data["kind"], name=request.data.get("name", request.data["kind"]),
            config=request.data.get("config", {}), encrypted_secret=encrypt_to_bytes(secret),
            workspace_token=secrets.token_urlsafe(24),
        )
        return Response({"id": str(integration.id), "workspace_token": integration.workspace_token, "signing_secret": secret}, status=201)


class WebhookIngressView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, integration, workspace_token):
        row = get_object_or_404(Integration, kind=integration, workspace_token=workspace_token, enabled=True)
        secret = decrypt_from_bytes(bytes(row.encrypted_secret)) if row.encrypted_secret else ""
        signature = (
            request.headers.get("X-Deep-Foundry-Signature")
            or request.headers.get("X-Agentarium-Signature")
            or request.headers.get("X-Hub-Signature-256", "")
        )
        expected = "sha256=" + hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return Response({"error": "invalid_signature"}, status=401)
        try:
            payload = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            payload = {"raw": request.body.decode(errors="replace")}
        triggers = WorkflowTrigger.objects.filter(
            workflow__workspace=row.workspace,
            trigger_type=WorkflowTrigger.TriggerType.EVENT,
            event_source__in=[integration, f"{integration}:{request.headers.get('X-GitHub-Event', '')}"],
            enabled=True,
        ).select_related("workflow__current_version")
        run_ids = [
            str(start_workflow_run(trigger.workflow, triggered_by=WorkflowRun.TriggeredBy.EVENT, context=payload).id)
            for trigger in triggers
        ]
        return Response({"accepted": True, "workflow_run_ids": run_ids}, status=202)


class ApiTokenListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        workspace = _workspace_for_write(request.user, workspace_id)
        return Response([{"id": str(row.id), "name": row.name, "prefix": row.token_prefix, "scopes": row.scopes, "last_used_at": row.last_used_at, "revoked_at": row.revoked_at} for row in workspace.api_tokens.all()])

    def post(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id)
        row, plaintext = create_api_token(workspace=workspace, user=request.user, name=request.data.get("name", "SDK token"), scopes=request.data.get("scopes", ["read"]))
        return Response({"id": str(row.id), "token": plaintext, "prefix": row.token_prefix, "scopes": row.scopes}, status=201)


class ApiTokenRevokeView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, workspace_id, token_id):
        workspace = _workspace_for_write(request.user, workspace_id)
        row = get_object_or_404(ApiToken, id=token_id, workspace=workspace)
        row.revoked_at = timezone.now()
        row.save(update_fields=["revoked_at"])
        return Response(status=204)


class SubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id)
        subscription, _ = Subscription.objects.get_or_create(workspace=workspace, defaults={"plan_tier": workspace.plan_tier})
        return Response({"plan_tier": subscription.plan_tier, "status": subscription.status, "seats": subscription.seats, "renews_at": subscription.renews_at})

    def patch(self, request, workspace_id):
        workspace = _workspace_for_write(request.user, workspace_id)
        tier = request.data.get("plan_tier")
        if tier not in Workspace.PlanTier.values:
            raise ValidationError({"plan_tier": "Invalid plan."})
        subscription, _ = Subscription.objects.update_or_create(
            workspace=workspace,
            defaults={"plan_tier": tier, "seats": request.data.get("seats"), "status": Subscription.Status.ACTIVE},
        )
        workspace.plan_tier = tier
        workspace.save(update_fields=["plan_tier"])
        return Response({"plan_tier": subscription.plan_tier, "status": subscription.status})


# --- Starter teams (templates + AI-designed) -------------------------------
# GET /team-templates, POST /workspaces/{id}/provision-team, and
# POST /workspaces/{id}/team-suggestions. Both provisioning inputs (a curated
# template key, or a reviewed spec — typically from ai.team_designer) funnel
# into core.starter_teams.provision_team.


class TeamTemplateListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        from core.starter_teams import template_catalog

        return Response(template_catalog())


class ProvisionTeamView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, workspace_id: str) -> Response:
        from core.starter_teams import provision_team, provision_template

        workspace = get_workspace_for_member(request.user, workspace_id)
        template_key = request.data.get("template")
        if template_key:
            result = provision_template(
                workspace=workspace, created_by=request.user, template_key=str(template_key)
            )
        else:
            result = provision_team(
                workspace=workspace,
                created_by=request.user,
                spec={
                    "team_name": request.data.get("team_name", ""),
                    "collaboration_pattern": request.data.get("collaboration_pattern", ""),
                    "coworkers": request.data.get("coworkers") or [],
                },
            )
        write_audit_log(
            actor_type="user", actor_id=request.user.id, action="starter_team.provision",
            resource_type="workspace", resource_id=workspace.id, workspace_id=workspace.id,
            metadata={
                "template": str(template_key) if template_key else None,
                "coworkers": [row["name"] for row in result["coworkers"]],
            },
        )
        return Response(result, status=status.HTTP_201_CREATED)


class TeamSuggestionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, workspace_id: str) -> Response:
        from ai.model_router.errors import AdapterError
        from ai.team_designer import TeamDesignError, design_team
        from core.interface import CredentialNotFoundError

        workspace = get_workspace_for_member(request.user, workspace_id)
        description = str(request.data.get("description", "")).strip()
        if not description:
            raise ValidationError({"description": "Describe the company or project first."})
        try:
            spec = design_team(workspace_id=workspace.id, description=description)
        except CredentialNotFoundError:
            return Response(
                {"error": {"code": "provider_credential_required", "message": "Add a DeepSeek API key under Settings → Model providers first.", "details": {}}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (TeamDesignError, AdapterError) as exc:
            return Response(
                {"error": {"code": "team_design_failed", "message": f"Couldn't design a team: {exc}", "details": {}}},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(spec)
