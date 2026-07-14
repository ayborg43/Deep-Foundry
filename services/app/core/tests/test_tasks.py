from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from ai.model_router.adapters.deepseek_cloud import DeepSeekCloudAdapter
from ai.task_engine import execute_background_task
from core.coworkers import create_coworker
from core.encryption import encrypt_to_bytes
from core.interface import decide_approval_request
from core.models import (
    ApprovalRequest,
    CoworkerToolAttachment,
    Notification,
    PermissionProfile,
    ProviderCredential,
    Task,
    Tool,
    User,
    Workspace,
    WorkspaceMember,
)
from worker.tasks import dispatch_notification_email


class TaskTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="task-owner@example.com", password="correct horse battery staple 42"
        )
        self.workspace = Workspace.objects.create(
            name="Tasks", type=Workspace.WorkspaceType.PERSONAL, owner=self.user
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace, user=self.user, role=WorkspaceMember.Role.OWNER
        )
        ProviderCredential.objects.create(
            workspace=self.workspace,
            deployment_mode=ProviderCredential.DeploymentMode.DEEPSEEK_CLOUD,
            encrypted_key=encrypt_to_bytes("fake-key"),
            label="Task tests",
            is_default=True,
        )
        profile = PermissionProfile.objects.create(workspace=self.workspace, name="Task profile")
        self.coworker = create_coworker(
            workspace=self.workspace,
            owner=self.user,
            created_by=self.user,
            name="Aria",
            role_description="Complete tasks carefully.",
            model_binding={"primary": "deepseek-chat"},
            permission_profile=profile,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def create_task(self) -> Task:
        return Task.objects.create(
            workspace=self.workspace,
            coworker=self.coworker,
            created_by_type=Task.CreatedByType.USER,
            created_by_id=self.user.id,
            title="Prepare report",
            description="Prepare the weekly report.",
        )


class TaskApiTests(TaskTestBase):
    @patch("core.task_views.execute_background_task.delay")
    def test_direct_creation_queues_worker_and_is_workspace_scoped(self, delay):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/v1/tasks",
                {
                    "workspace_id": str(self.workspace.id),
                    "coworker_id": str(self.coworker.id),
                    "title": "Prepare report",
                    "description": "Prepare the weekly report.",
                },
                format="json",
            )
        self.assertEqual(response.status_code, 202)
        task = Task.objects.get(id=response.data["id"])
        self.assertEqual(task.status, Task.Status.PENDING)
        delay.assert_called_once_with(str(task.id))

        listing = self.client.get(f"/api/v1/tasks?workspace_id={self.workspace.id}")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data[0]["coworker_name"], "Aria")


class TaskEngineTests(TaskTestBase):
    @patch("worker.tasks.dispatch_notification_email.delay")
    @patch.object(DeepSeekCloudAdapter, "_post")
    def test_simple_task_completes_and_notifies(self, post, _email_delay):
        post.return_value = {
            "model": "deepseek-chat",
            "choices": [{"message": {"content": "Weekly report complete."}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4},
        }
        task = self.create_task()
        execute_background_task(task.id)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.COMPLETED)
        self.assertEqual(task.result, "Weekly report complete.")
        self.assertTrue(
            Notification.objects.filter(
                user=self.user, type=Notification.Type.TASK_COMPLETED
            ).exists()
        )

    @patch("worker.tasks.dispatch_notification_email.delay")
    @patch.object(DeepSeekCloudAdapter, "_post")
    def test_dangerous_tool_pauses_then_resumes_after_approval(self, post, _email_delay):
        CoworkerToolAttachment.objects.create(
            coworker=self.coworker, tool=Tool.objects.get(name="execute_code"), enabled=True
        )
        post.side_effect = [
            {
                "model": "deepseek-chat",
                "choices": [{
                    "message": {
                        "content": "",
                        "tool_calls": [{
                            "id": "call_task_1",
                            "type": "function",
                            "function": {"name": "execute_code", "arguments": '{"code":"print(1)"}'},
                        }],
                    },
                    "finish_reason": "tool_calls",
                }],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4},
            },
            {
                "model": "deepseek-chat",
                "choices": [{"message": {"content": "Task finished safely."}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 15, "completion_tokens": 5},
            },
        ]
        task = self.create_task()
        execute_background_task(task.id)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.NEEDS_APPROVAL)
        approval = ApprovalRequest.objects.get(task_id=task.id)
        self.assertEqual(approval.requested_action["tool_call_id"], "call_task_1")

        decide_approval_request(approval.id, approve=True, decided_by_user_id=self.user.id)
        execute_background_task(task.id)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.COMPLETED)
        self.assertEqual(task.result, "Task finished safely.")


class NotificationEmailTests(TaskTestBase):
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_delivery_is_idempotent(self):
        notification = Notification.objects.create(
            workspace=self.workspace,
            user=self.user,
            type=Notification.Type.TASK_COMPLETED,
            payload={"task_id": str(self.user.id), "title": "Report", "status": "completed"},
        )
        dispatch_notification_email(str(notification.id))
        dispatch_notification_email(str(notification.id))
        notification.refresh_from_db()
        self.assertIsNotNone(notification.email_sent_at)
        self.assertEqual(len(mail.outbox), 1)
