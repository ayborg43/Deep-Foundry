import json
from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ai.model_router.adapters.deepseek_cloud import DeepSeekCloudAdapter
from ai.model_router.errors import AdapterError
from ai.models import Conversation, ConversationParticipant, Message
from core.coworkers import create_coworker
from core.encryption import encrypt_to_bytes
from core.models import (
    ApprovalPolicy,
    ApprovalRequest,
    AuditLog,
    PermissionProfile,
    ProviderCredential,
    Tool,
    User,
    Workspace,
    WorkspaceMember,
)

VALID_PASSWORD = "correct horse battery staple 42"


def _stream(*events: dict):
    return iter(events)


def _tool_call_chunk(tool_call_id: str, name: str, arguments_json: str) -> dict:
    return {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": tool_call_id,
                            "function": {"name": name, "arguments": arguments_json},
                        }
                    ]
                },
                "finish_reason": None,
            }
        ]
    }


def _finish_chunk(finish_reason: str) -> dict:
    return {"choices": [{"delta": {}, "finish_reason": finish_reason}]}


def _content_chunk(text: str) -> dict:
    return {"choices": [{"delta": {"content": text}, "finish_reason": None}]}


def _parse_sse(streaming_content) -> list[tuple[str, dict]]:
    raw = b"".join(streaming_content).decode()
    events = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        event_name, data = None, None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_name = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        if event_name:
            events.append((event_name, data))
    return events


class ChatTestBase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="chatowner@example.com", password=VALID_PASSWORD
        )
        self.stranger = User.objects.create_user(
            email="chatstranger@example.com", password=VALID_PASSWORD
        )
        self.workspace = Workspace.objects.create(
            name="Chat WS", type=Workspace.WorkspaceType.PERSONAL, owner=self.owner
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace, user=self.owner, role=WorkspaceMember.Role.OWNER
        )
        ProviderCredential.objects.create(
            workspace=self.workspace,
            deployment_mode=ProviderCredential.DeploymentMode.DEEPSEEK_CLOUD,
            encrypted_key=encrypt_to_bytes("fake-api-key"),
            label="test credential",
            is_default=True,
        )
        self.permission_profile = PermissionProfile.objects.create(
            workspace=self.workspace, name="Test Profile"
        )
        self.coworker = create_coworker(
            workspace=self.workspace,
            owner=self.owner,
            created_by=self.owner,
            name="Aria",
            role_description="A helpful test coworker.",
            model_binding={"primary": "deepseek-v4-flash"},
            permission_profile=self.permission_profile,
        )
        from core.models import CoworkerToolAttachment

        CoworkerToolAttachment.objects.create(
            coworker=self.coworker, tool=Tool.objects.get(name="web_search"), enabled=True
        )
        CoworkerToolAttachment.objects.create(
            coworker=self.coworker, tool=Tool.objects.get(name="execute_code"), enabled=True
        )
        # Approval-summary generation makes a non-streaming _post call after
        # a tool is gated. Fail it fast by default — summaries degrade to
        # blank — so no test here can reach the live API; tests asserting
        # summaries override this patch with a scripted response.
        post_patcher = patch.object(
            DeepSeekCloudAdapter,
            "_post",
            side_effect=AdapterError("no non-streaming calls in tests"),
        )
        post_patcher.start()
        self.addCleanup(post_patcher.stop)
        self._auth_as(self.owner)

    def _auth_as(self, user, password=VALID_PASSWORD):
        login = self.client.post(reverse("auth-login"), {"email": user.email, "password": password})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['tokens']['access']}")

    def _send(self, conversation, content) -> list[tuple[str, dict]]:
        """POSTs a message and immediately consumes the streamed response.
        StreamingHttpResponse content is lazy — Django's test client doesn't
        auto-consume it, so nothing inside the orchestrator (not even the
        user Message row) actually executes until something iterates
        `.streaming_content`. Must be called while any relevant mock is
        still active: the real _post_stream would otherwise run once the
        mock's `with` block exits, since method lookup happens at
        generator-iteration time, not at call time."""
        response = self.client.post(
            reverse("conversation-message-list-send", kwargs={"conversation_id": conversation.id}),
            {"content": content},
        )
        return _parse_sse(response.streaming_content)

    def _create_conversation(self) -> Conversation:
        response = self.client.post(
            reverse("conversation-list-create"),
            {"workspace_id": str(self.workspace.id), "coworker_id": str(self.coworker.id)},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return Conversation.objects.get(id=response.data["id"])


class ConversationCrudTests(ChatTestBase):
    def test_create_conversation_creates_participants(self):
        conversation = self._create_conversation()
        participant_types = set(
            ConversationParticipant.objects.filter(conversation=conversation).values_list(
                "participant_type", flat=True
            )
        )
        self.assertEqual(participant_types, {"user", "coworker"})
        self.assertTrue(AuditLog.objects.filter(action="conversation.create").exists())

    def test_list_conversations_requires_workspace_id(self):
        response = self.client.get(reverse("conversation-list-create"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_conversations_scoped_to_workspace(self):
        self._create_conversation()
        response = self.client.get(
            reverse("conversation-list-create"), {"workspace_id": str(self.workspace.id)}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_stranger_cannot_create_conversation(self):
        self._auth_as(self.stranger)
        response = self.client.post(
            reverse("conversation-list-create"),
            {"workspace_id": str(self.workspace.id), "coworker_id": str(self.coworker.id)},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_stranger_cannot_read_conversation(self):
        conversation = self._create_conversation()
        self._auth_as(self.stranger)
        response = self.client.get(
            reverse("conversation-detail", kwargs={"conversation_id": conversation.id})
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class MessageSendStreamTests(ChatTestBase):
    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_send_message_streams_tokens_and_completes(self, mock_stream):
        mock_stream.return_value = _stream(_content_chunk("Hi there"), _finish_chunk("stop"))
        conversation = self._create_conversation()

        response = self.client.post(
            reverse("conversation-message-list-send", kwargs={"conversation_id": conversation.id}),
            {"content": "Hello"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        events = _parse_sse(response.streaming_content)
        self.assertEqual([e for e, _ in events], ["token", "message_complete"])
        self.assertEqual(events[-1][1]["content"], "Hi there")

    def test_send_message_requires_content(self):
        conversation = self._create_conversation()
        response = self.client.post(
            reverse("conversation-message-list-send", kwargs={"conversation_id": conversation.id}),
            {"content": ""},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_get_lists_message_history(self, mock_stream):
        mock_stream.return_value = _stream(_content_chunk("Hi"), _finish_chunk("stop"))
        conversation = self._create_conversation()
        self._send(conversation, "Hello")
        response = self.client.get(
            reverse("conversation-message-list-send", kwargs={"conversation_id": conversation.id})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_stranger_cannot_send_message(self):
        conversation = self._create_conversation()
        self._auth_as(self.stranger)
        response = self.client.post(
            reverse("conversation-message-list-send", kwargs={"conversation_id": conversation.id}),
            {"content": "Hello"},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ApprovalGateHttpTests(ChatTestBase):
    """End-to-end, over real HTTP requests: send -> approval_required ->
    approve/deny -> resume stream -> message_complete, all logged to
    audit_log — the exact exit criteria from IMPLEMENTATION_PLAN.md
    Milestone 4 Epic 4.3."""

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_full_approve_flow(self, mock_stream):
        mock_stream.return_value = _stream(
            _tool_call_chunk("call_1", "execute_code", "{}"), _finish_chunk("tool_calls")
        )
        conversation = self._create_conversation()
        events = self._send(conversation, "run some code")
        self.assertEqual([e for e, _ in events], ["approval_required"])
        approval_request_id = events[0][1]["approval_request_id"]

        approval = ApprovalRequest.objects.get(id=approval_request_id)
        self.assertEqual(approval.status, ApprovalRequest.Status.PENDING)

        approve_response = self.client.post(
            reverse("approval-request-approve", kwargs={"approval_request_id": approval_request_id})
        )
        self.assertEqual(approve_response.status_code, status.HTTP_200_OK, approve_response.data)
        self.assertEqual(approve_response.data["status"], "approved")
        self.assertTrue(
            AuditLog.objects.filter(action="approval_request.approved").exists()
        )

        with patch.object(DeepSeekCloudAdapter, "_post_stream") as mock_stream2:
            mock_stream2.return_value = _stream(_content_chunk("Done."), _finish_chunk("stop"))
            resume_response = self.client.get(
                reverse("conversation-message-stream", kwargs={"conversation_id": conversation.id})
            )
            resume_events = _parse_sse(resume_response.streaming_content)
        self.assertEqual(
            [e for e, _ in resume_events],
            ["tool_call_started", "tool_call_result", "token", "message_complete"],
        )
        self.assertTrue(AuditLog.objects.filter(action="tool.executed").exists())

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_full_deny_flow(self, mock_stream):
        mock_stream.return_value = _stream(
            _tool_call_chunk("call_1", "execute_code", "{}"), _finish_chunk("tool_calls")
        )
        conversation = self._create_conversation()
        approval_request_id = self._send(conversation, "run some code")[0][1]["approval_request_id"]

        deny_response = self.client.post(
            reverse("approval-request-deny", kwargs={"approval_request_id": approval_request_id})
        )
        self.assertEqual(deny_response.status_code, status.HTTP_200_OK)
        self.assertEqual(deny_response.data["status"], "denied")
        self.assertTrue(AuditLog.objects.filter(action="approval_request.denied").exists())
        self.assertFalse(AuditLog.objects.filter(action="tool.executed").exists())

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_stranger_cannot_approve(self, mock_stream):
        mock_stream.return_value = _stream(
            _tool_call_chunk("call_1", "execute_code", "{}"), _finish_chunk("tool_calls")
        )
        conversation = self._create_conversation()
        approval_request_id = self._send(conversation, "run some code")[0][1]["approval_request_id"]

        self._auth_as(self.stranger)
        response = self.client.post(
            reverse("approval-request-approve", kwargs={"approval_request_id": approval_request_id})
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            ApprovalRequest.objects.get(id=approval_request_id).status,
            ApprovalRequest.Status.PENDING,
        )

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_deciding_twice_returns_400(self, mock_stream):
        mock_stream.return_value = _stream(
            _tool_call_chunk("call_1", "execute_code", "{}"), _finish_chunk("tool_calls")
        )
        conversation = self._create_conversation()
        approval_request_id = self._send(conversation, "run some code")[0][1]["approval_request_id"]

        first = self.client.post(
            reverse("approval-request-approve", kwargs={"approval_request_id": approval_request_id})
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        second = self.client.post(
            reverse("approval-request-deny", kwargs={"approval_request_id": approval_request_id})
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        # The second (denied) call must not have overwritten the first decision.
        self.assertEqual(
            ApprovalRequest.objects.get(id=approval_request_id).status,
            ApprovalRequest.Status.APPROVED,
        )

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_approval_request_list_filters_by_status(self, mock_stream):
        mock_stream.return_value = _stream(
            _tool_call_chunk("call_1", "execute_code", "{}"), _finish_chunk("tool_calls")
        )
        conversation = self._create_conversation()
        self._send(conversation, "run some code")
        response = self.client.get(
            reverse("approval-request-list", kwargs={"workspace_id": self.workspace.id}),
            {"status": "pending"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["tool_name"], "execute_code")


class MessagePatchRegenerateTests(ChatTestBase):
    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_patch_own_message(self, mock_stream):
        mock_stream.return_value = _stream(_content_chunk("Hi"), _finish_chunk("stop"))
        conversation = self._create_conversation()
        self._send(conversation, "Hello")
        user_message = Message.objects.get(sender_type=Message.SenderType.USER)
        response = self.client.patch(
            reverse("message-patch", kwargs={"message_id": user_message.id}),
            {"content": "Hello, edited"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user_message.refresh_from_db()
        self.assertEqual(user_message.content, "Hello, edited")

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_cannot_patch_coworker_message(self, mock_stream):
        mock_stream.return_value = _stream(_content_chunk("Hi"), _finish_chunk("stop"))
        conversation = self._create_conversation()
        self._send(conversation, "Hello")
        coworker_message = Message.objects.get(sender_type=Message.SenderType.COWORKER)
        response = self.client.patch(
            reverse("message-patch", kwargs={"message_id": coworker_message.id}),
            {"content": "hacked"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_regenerate_completed_coworker_message(self, mock_stream):
        mock_stream.return_value = _stream(_content_chunk("First answer"), _finish_chunk("stop"))
        conversation = self._create_conversation()
        self._send(conversation, "Hello")
        original = Message.objects.get(sender_type=Message.SenderType.COWORKER)

        with patch.object(DeepSeekCloudAdapter, "_post_stream") as mock_stream2:
            mock_stream2.return_value = _stream(
                _content_chunk("Second answer"), _finish_chunk("stop")
            )
            response = self.client.post(
                reverse("message-regenerate", kwargs={"message_id": original.id})
            )
            events = _parse_sse(response.streaming_content)
        self.assertEqual(events[-1][1]["content"], "Second answer")

        # Original untouched — regeneration is additive, not destructive.
        original.refresh_from_db()
        self.assertEqual(original.content, "First answer")
        new_message = Message.objects.get(content="Second answer")
        self.assertEqual(new_message.parent_message_id, original.id)


class ApprovalPolicyApiTests(ChatTestBase):
    def _policies_url(self) -> str:
        return f"/api/v1/workspaces/{self.workspace.id}/approval-policies"

    def test_create_list_delete_policy(self):
        tool = Tool.objects.get(name="execute_code")
        created = self.client.post(
            self._policies_url(),
            {
                "tool_id": str(tool.id),
                "coworker_id": str(self.coworker.id),
                "argument_path": "amount",
                "max_amount": "250",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["tool_name"], "execute_code")
        self.assertEqual(created.data["max_amount"], "250")

        listed = self.client.get(self._policies_url())
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data), 1)

        deleted = self.client.delete(f"/api/v1/approval-policies/{created.data['id']}")
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(ApprovalPolicy.objects.exists())
        self.assertTrue(
            AuditLog.objects.filter(action="approval_policy.created").exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(action="approval_policy.deleted").exists()
        )

    def test_condition_requires_both_path_and_amount(self):
        tool = Tool.objects.get(name="execute_code")
        response = self.client.post(
            self._policies_url(),
            {"tool_id": str(tool.id), "argument_path": "amount"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_stranger_cannot_list_policies(self):
        self._auth_as(self.stranger)
        response = self.client.get(self._policies_url())
        self.assertIn(response.status_code, (403, 404))
