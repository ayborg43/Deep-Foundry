import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.coworkers import create_coworker
from core.models import (
    AgentTeam, Integration, MarketplaceListing, OrgPolicyFloor, PermissionProfile,
    WorkflowRun, WorkflowRunStep, WorkflowTrigger, Workspace, WorkspaceMember, User,
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


class MarketplaceAndSdkTests(Phase2TestBase):
    def test_first_party_pack_install_provisions_team_and_scheduled_workflow(self):
        listing = MarketplaceListing.objects.get(name="Developer Team")
        response = self.client.post(f"/api/v1/marketplace/listings/{listing.id}/install", {"workspace_id": str(self.workspace.id)}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(self.workspace.agent_teams.filter(name="Developer Team").exists())
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
