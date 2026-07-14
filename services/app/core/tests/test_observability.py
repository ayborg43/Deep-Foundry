from decimal import Decimal
from uuid import uuid4

from django.db import DatabaseError, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from ai.models import ModelCall
from core.coworkers import create_coworker
from core.interface import write_audit_log
from core.models import AuditLog, User, Workspace, WorkspaceMember


class ObservabilityApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@example.com", password="test-password-42")
        self.member = User.objects.create_user(email="member@example.com", password="test-password-42")
        self.workspace = Workspace.objects.create(
            name="Observed workspace", type=Workspace.WorkspaceType.PERSONAL, owner=self.owner
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace, user=self.owner, role=WorkspaceMember.Role.OWNER
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace, user=self.member, role=WorkspaceMember.Role.MEMBER
        )
        self.coworker = create_coworker(
            workspace=self.workspace,
            owner=self.owner,
            created_by=self.owner,
            name="Ada",
            role_description="Analyze usage.",
            model_binding={"primary": "deepseek-v4-flash"},
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_audit_log_is_filtered_and_restricted_to_admins(self):
        matching = write_audit_log(
            workspace_id=self.workspace.id,
            actor_type=AuditLog.ActorType.COWORKER,
            actor_id=self.coworker.id,
            action="model.call",
            resource_type="model_call",
            resource_id=uuid4(),
            metadata={"coworker_id": str(self.coworker.id)},
        )
        write_audit_log(
            workspace_id=self.workspace.id,
            actor_type=AuditLog.ActorType.USER,
            actor_id=self.owner.id,
            action="workspace.updated",
            resource_type="workspace",
            resource_id=self.workspace.id,
        )

        response = self.client.get(
            f"/api/v1/workspaces/{self.workspace.id}/audit-log",
            {"action": "model", "coworker_id": str(self.coworker.id)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(matching.id))
        self.assertEqual(response.data["results"][0]["actor_label"], "Ada")

        self.client.force_authenticate(self.member)
        denied = self.client.get(f"/api/v1/workspaces/{self.workspace.id}/audit-log")
        self.assertEqual(denied.status_code, 403)

    def test_usage_rollup_groups_calls_by_coworker_and_provider(self):
        for model_id, mode, cost, input_tokens, output_tokens in (
            ("deepseek-v4-flash", "deepseek_cloud", "0.010000", 100, 20),
            ("local-qwen", "local", "0.020000", 50, 10),
        ):
            ModelCall.objects.create(
                request_id=uuid4(),
                workspace=self.workspace,
                coworker=self.coworker,
                deployment_mode=mode,
                model_id=model_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=Decimal(cost),
                latency_ms=100,
                status=ModelCall.Status.SUCCESS,
            )

        response = self.client.get(f"/api/v1/workspaces/{self.workspace.id}/usage?range=30d")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["totals"]["calls"], 2)
        self.assertEqual(Decimal(response.data["totals"]["cost_usd"]), Decimal("0.030000"))
        self.assertEqual(response.data["by_coworker"][0]["coworker_name"], "Ada")
        self.assertEqual(len(response.data["by_provider"]), 2)
        self.assertEqual(len(response.data["daily"]), 1)

    @override_settings(INTERNAL_API_TOKEN="test-internal-secret")
    def test_internal_audit_ingestion_requires_service_token(self):
        payload = {
            "workspace_id": str(self.workspace.id),
            "actor_type": "system",
            "action": "worker.started",
            "resource_type": "task",
            "resource_id": str(uuid4()),
            "metadata": {"request_id": "request-1"},
        }
        denied = self.client.post("/internal/v1/audit-log", payload, format="json")
        self.assertEqual(denied.status_code, 403)
        accepted = self.client.post(
            "/internal/v1/audit-log",
            payload,
            format="json",
            HTTP_X_INTERNAL_TOKEN="test-internal-secret",
        )
        self.assertEqual(accepted.status_code, 201)
        self.assertTrue(AuditLog.objects.filter(id=accepted.data["id"], action="worker.started").exists())


class AuditLogImmutabilityTests(TransactionTestCase):
    reset_sequences = False

    def test_database_rejects_updates_and_deletes(self):
        row = write_audit_log(
            actor_type=AuditLog.ActorType.SYSTEM,
            actor_id=None,
            action="system.started",
            resource_type="system",
            resource_id=None,
        )
        with self.assertRaises(DatabaseError), transaction.atomic():
            AuditLog.objects.filter(id=row.id).update(action="tampered")
        with self.assertRaises(DatabaseError), transaction.atomic():
            AuditLog.objects.filter(id=row.id).delete()
        row.refresh_from_db()
        self.assertEqual(row.action, "system.started")
