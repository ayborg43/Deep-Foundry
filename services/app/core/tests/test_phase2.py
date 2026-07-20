import hashlib
import hmac
import importlib
import json
from datetime import timedelta
from unittest.mock import patch

from django.apps import apps as django_apps
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.coworkers import create_coworker
from core.models import (
    AgentTeam, Integration, MarketplaceListing, MarketplaceListingVersion, Notification,
    OrgPolicyFloor, PermissionProfile,
    Task, WorkflowRun, WorkflowRunStep, WorkflowTrigger, Workspace, WorkspaceMember, User,
)
from core.permissions import resolve_tool_permission
from core.v2_engine import advance_workflow_run, evaluate_due_triggers
from core.v2_services import create_agent_team, create_api_token, create_workflow, start_workflow_run


class Phase2TestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="owner-v2@example.com", password="test-pass-phrase-123")
        self.workspace = Workspace.objects.create(name="V2 Org", type=Workspace.WorkspaceType.ORGANIZATION, owner=self.user)
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role=WorkspaceMember.Role.OWNER)
        profile = PermissionProfile.objects.create(workspace=self.workspace, name="Default")
        self.manager = create_coworker(workspace=self.workspace, owner=self.user, created_by=self.user, name="Manager", role_description="Manage work.", model_binding={"primary": "deepseek-v4-flash"}, permission_profile=profile)
        self.worker = create_coworker(workspace=self.workspace, owner=self.user, created_by=self.user, name="Worker", role_description="Do work.", model_binding={"primary": "deepseek-v4-flash"}, permission_profile=profile)
        self.client = APIClient(); self.client.force_authenticate(self.user)


class OrganizationAndTeamTests(Phase2TestBase):
    def test_policy_floor_can_only_make_execution_stricter(self):
        OrgPolicyFloor.objects.create(workspace=self.workspace, tool_risk_classification="safe", min_required_policy="approval")
        self.assertEqual(resolve_tool_permission("safe", {"safe": "auto"}, {"safe": "approval"}), "approval")
        self.assertEqual(resolve_tool_permission("dangerous", {"dangerous": "auto"}, {}), "approval")

    @patch("worker.tasks.execute_agent_team_run.delay")
    def test_manager_delegate_team_is_versioned_and_runnable(self, delay):
        team = create_agent_team(workspace=self.workspace, user=self.user, payload={"name": "Delivery", "collaboration_pattern": "manager_delegate", "members": [{"coworker_id": str(self.manager.id), "role": "manager"}, {"coworker_id": str(self.worker.id), "role": "developer"}]})
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/api/v1/agent-teams/{team.id}/run", {"objective": "Ship a tested release."}, format="json")
        self.assertEqual(response.status_code, 202); self.assertEqual(team.current_version.version_number, 1)
        delay.assert_called_once()


class WorkflowTests(Phase2TestBase):
    @patch("worker.tasks.execute_workflow_run.delay")
    def test_due_scheduler_locks_trigger_without_locking_nullable_workflow_joins(self, delay):
        workflow = create_workflow(
            workspace=self.workspace,
            user=self.user,
            name="Scheduled",
            definition={"steps": [{"type": "human_checkpoint", "title": "Review"}]},
        )
        previous_run_at = timezone.now() - timedelta(minutes=1)
        trigger = WorkflowTrigger.objects.create(
            workflow=workflow,
            trigger_type=WorkflowTrigger.TriggerType.SCHEDULED,
            schedule_cron="*/5 * * * *",
            next_run_at=previous_run_at,
        )

        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(evaluate_due_triggers(), 1)

        trigger.refresh_from_db()
        self.assertGreater(trigger.next_run_at, previous_run_at)
        self.assertEqual(
            WorkflowRun.objects.filter(
                workflow_version=workflow.current_version,
                triggered_by=WorkflowRun.TriggeredBy.SCHEDULE,
            ).count(),
            1,
        )
        delay.assert_called_once()

    @patch("worker.tasks.execute_workflow_run.delay")
    def test_human_checkpoint_pauses_and_resumes_durable_run(self, delay):
        workflow = create_workflow(workspace=self.workspace, user=self.user, name="Approval", definition={"steps": [{"type": "human_checkpoint", "title": "Approve"}]})
        with self.captureOnCommitCallbacks(execute=True):
            run = start_workflow_run(workflow, triggered_by=WorkflowRun.TriggeredBy.USER)
        advance_workflow_run(str(run.id)); run.refresh_from_db()
        step = run.steps.get(); self.assertEqual(run.status, WorkflowRun.Status.NEEDS_APPROVAL)
        response = self.client.post(f"/api/v1/workflow-runs/{run.id}/steps/{step.id}/approve", {}, format="json")
        self.assertEqual(response.status_code, 200); run.refresh_from_db(); self.assertEqual(run.current_step_index, 1)

    @patch("worker.tasks.dispatch_notification_email.delay")
    @patch("worker.tasks.execute_background_task.delay")
    @patch("worker.tasks.execute_workflow_run.delay")
    def test_failed_workflow_notifies_workspace_once(
        self, _workflow_delay, _task_delay, notification_delay
    ):
        workflow = create_workflow(
            workspace=self.workspace,
            user=self.user,
            name="Critical workflow",
            definition={
                "steps": [
                    {
                        "type": "coworker_action",
                        "coworker_id": str(self.worker.id),
                        "title": "Run critical step",
                        "instructions": "Complete the step.",
                    }
                ]
            },
        )
        run = start_workflow_run(
            workflow, triggered_by=WorkflowRun.TriggeredBy.USER
        )
        advance_workflow_run(str(run.id))
        task = Task.objects.get(created_by_id=run.id)
        task.status = Task.Status.FAILED
        task.error_message = "Sensitive internal failure detail"
        task.save(update_fields=["status", "error_message", "updated_at"])

        advance_workflow_run(str(run.id))
        advance_workflow_run(str(run.id))
        run.refresh_from_db()
        self.assertEqual(run.status, WorkflowRun.Status.FAILED)
        notifications = Notification.objects.filter(
            workspace=self.workspace,
            type=Notification.Type.WORKFLOW_FAILED,
        )
        self.assertEqual(notifications.count(), 1)
        self.assertNotIn(
            "Sensitive internal failure detail",
            json.dumps(notifications.get().payload),
        )
        notification_delay.assert_called_once()


class MarketplaceAndSdkTests(Phase2TestBase):
    def test_web_researcher_install_assigns_skill_and_declared_tools(self):
        listing = MarketplaceListing.objects.get(name="Web Researcher")
        response = self.client.post(
            f"/api/v1/marketplace/listings/{listing.id}/install",
            {
                "workspace_id": str(self.workspace.id),
                "coworker_id": str(self.worker.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["coworker_id"], str(self.worker.id))
        self.assertTrue(
            self.worker.skill_attachments.filter(
                skill__listing_version__listing=listing,
                enabled=True,
            ).exists()
        )
        self.assertEqual(
            set(
                self.worker.tool_attachments.filter(
                    tool__name__in=["web_search", "read_webpage"],
                    enabled=True,
                ).values_list("tool__name", flat=True)
            ),
            {"web_search", "read_webpage"},
        )

    def test_remove_demo_packs_handles_a_backfilled_default_coworker(self):
        demo_user = User.objects.create_user(
            email="marketplace@agentarium.local",
            password=None,
            display_name="Deep-Foundry",
            is_active=False,
        )
        demo_workspace = Workspace.objects.create(
            name="Deep-Foundry First Party",
            type=Workspace.WorkspaceType.ORGANIZATION,
            owner=demo_user,
        )
        profile = PermissionProfile.objects.create(
            workspace=demo_workspace,
            name="Default",
        )
        create_coworker(
            workspace=demo_workspace,
            owner=demo_user,
            created_by=demo_user,
            name="General Assistant",
            role_description="A backfilled default coworker.",
            model_binding={"primary": "deepseek-v4-flash"},
            permission_profile=profile,
        )

        migration = importlib.import_module(
            "core.migrations.0025_remove_demo_marketplace_packs"
        )
        migration.remove_demo_packs(django_apps, schema_editor=None)

        self.assertFalse(User.objects.filter(id=demo_user.id).exists())
        self.assertFalse(Workspace.objects.filter(id=demo_workspace.id).exists())

    def test_first_party_pack_install_provisions_team_and_scheduled_workflow(self):
        listing = MarketplaceListing.objects.create(
            publisher_workspace=self.workspace,
            listing_type="capability_pack",
            name="Test Delivery Team",
            summary="A test-only installable pack.",
        )
        MarketplaceListingVersion.objects.create(
            listing=listing,
            version_string="1.0.0",
            manifest={
                "declared_tools": [],
                "coworkers": [
                    {
                        "key": "manager",
                        "name": "Pack Manager",
                        "team_role": "manager",
                        "role_description": "Coordinate delivery.",
                    },
                    {
                        "key": "developer",
                        "name": "Pack Developer",
                        "team_role": "developer",
                        "role_description": "Implement delivery work.",
                    },
                ],
                "agent_team": {
                    "name": "Test Delivery Team",
                    "collaboration_pattern": "manager_delegate",
                },
                "workflows": [
                    {
                        "name": "Weekly delivery",
                        "schedule_cron": "0 9 * * 1",
                        "steps": [
                            {
                                "type": "coworker_action",
                                "coworker_ref": "developer",
                                "title": "Prepare delivery update",
                            }
                        ],
                    }
                ],
            },
            review_status="approved",
            reviewed_at=timezone.now(),
            published_at=timezone.now(),
        )
        response = self.client.post(f"/api/v1/marketplace/listings/{listing.id}/install", {"workspace_id": str(self.workspace.id)}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(self.workspace.agent_teams.filter(name="Test Delivery Team").exists())
        self.assertTrue(self.workspace.workflows.filter(triggers__trigger_type="scheduled").exists())

    def test_scoped_sdk_token_can_publish_safe_skill(self):
        _, token = create_api_token(workspace=self.workspace, user=self.user, name="Publisher", scopes=["publish"])
        client = APIClient(); client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        listing = client.post("/api/v1/marketplace/listings", {"publisher_workspace_id": str(self.workspace.id), "listing_type": "skill", "name": "Brief Writer", "summary": "Writes concise briefs."}, format="json")
        self.assertEqual(listing.status_code, 201)
        version = client.post(f"/api/v1/marketplace/listings/{listing.data['id']}/versions", {"version_string": "1.0.0", "manifest": {"declared_tools": []}, "instruction_content": "Write concise evidence-grounded briefs and preserve source citations."}, format="json")
        self.assertEqual(version.status_code, 201); self.assertEqual(version.data["review_status"], "approved")


class WebhookTests(Phase2TestBase):
    def test_signed_webhook_rejects_tampering_and_accepts_valid_body(self):
        response = self.client.post("/api/v1/integrations", {"workspace_id": str(self.workspace.id), "kind": "webhook", "name": "Events", "secret": "shared-secret"}, format="json")
        token = response.data["workspace_token"]; body = json.dumps({"event": "ready"}).encode()
        signature = "sha256=" + hmac.new(b"shared-secret", body, hashlib.sha256).hexdigest()
        accepted = self.client.generic("POST", f"/api/v1/webhooks/webhook/{token}", body, content_type="application/json", HTTP_X_AGENTARIUM_SIGNATURE=signature)
        self.assertEqual(accepted.status_code, 202)
        denied = self.client.generic("POST", f"/api/v1/webhooks/webhook/{token}", body, content_type="application/json", HTTP_X_AGENTARIUM_SIGNATURE="sha256=bad")
        self.assertEqual(denied.status_code, 401)
