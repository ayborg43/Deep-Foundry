"""
Chat orchestrator tests — the security-critical surface of Milestone 4.
Every test mocks DeepSeekCloudAdapter._post_stream (the network boundary,
same pattern as ai/tests/test_adapter.py) so these run against a real
Postgres test DB but never touch the live DeepSeek API.
"""

import json
import threading
import time
from unittest.mock import patch

from django.db import connection
from django.test import TestCase, TransactionTestCase

from ai.chat_orchestrator import _advance_message_tool_calls, resume_turn, start_turn
from ai.model_router.adapters.deepseek_cloud import DeepSeekCloudAdapter
from ai.model_router.errors import AdapterError
from ai.models import Conversation, ConversationParticipant, Message
from ai.tool_executor import ToolResult
from core.coworkers import create_coworker
from core.encryption import encrypt_to_bytes
from core.interface import ToolInfo, create_approval_request, decide_approval_request, get_coworker_config
from decimal import Decimal

from core.models import (
    ApprovalPolicy,
    ApprovalRequest,
    AuditLog,
    CoworkerToolAttachment,
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


def _tool_call_chunk(tool_call_id: str, name: str, arguments_json: str, index: int = 0) -> dict:
    return {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": index,
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


class ChatOrchestratorTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="chatuser@example.com", password=VALID_PASSWORD)
        self.workspace = Workspace.objects.create(
            name="Chat WS", type=Workspace.WorkspaceType.PERSONAL, owner=self.user
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace, user=self.user, role=WorkspaceMember.Role.OWNER
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
            owner=self.user,
            created_by=self.user,
            name="Aria",
            role_description="A helpful test coworker.",
            model_binding={"primary": "deepseek-v4-flash"},
            permission_profile=self.permission_profile,
        )
        CoworkerToolAttachment.objects.create(
            coworker=self.coworker, tool=Tool.objects.get(name="web_search"), enabled=True
        )
        CoworkerToolAttachment.objects.create(
            coworker=self.coworker, tool=Tool.objects.get(name="execute_code"), enabled=True
        )
        self.conversation = Conversation.objects.create(
            workspace=self.workspace, created_by=self.user, title="Test conversation"
        )
        ConversationParticipant.objects.create(
            conversation=self.conversation,
            participant_type=ConversationParticipant.ParticipantType.USER,
            participant_id=self.user.id,
        )
        ConversationParticipant.objects.create(
            conversation=self.conversation,
            participant_type=ConversationParticipant.ParticipantType.COWORKER,
            participant_id=self.coworker.id,
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

    def _start_turn(self, content="Hello"):
        return list(
            start_turn(
                conversation=self.conversation,
                coworker_id=self.coworker.id,
                workspace_id=self.workspace.id,
                user_id=self.user.id,
                content=content,
            )
        )

    def _resume_turn(self):
        return list(
            resume_turn(
                conversation=self.conversation,
                coworker_id=self.coworker.id,
                workspace_id=self.workspace.id,
            )
        )


class SimpleResponseTests(ChatOrchestratorTestBase):
    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_simple_response_no_tools(self, mock_stream):
        mock_stream.return_value = _stream(
            _content_chunk("Hello"), _content_chunk(" there"), _finish_chunk("stop")
        )
        events = self._start_turn()
        self.assertEqual([e.event for e in events], ["token", "token", "message_complete"])
        self.assertEqual(events[-1].data["content"], "Hello there")

        messages = list(
            Message.objects.filter(conversation=self.conversation).order_by("created_at")
        )
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].sender_type, Message.SenderType.USER)
        self.assertEqual(messages[0].content, "Hello")
        self.assertEqual(messages[1].sender_type, Message.SenderType.COWORKER)
        self.assertEqual(messages[1].content, "Hello there")
        self.assertEqual(messages[1].status, Message.Status.COMPLETE)

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_missing_coworker_yields_error_event(self, mock_stream):
        events = list(
            start_turn(
                conversation=self.conversation,
                coworker_id="00000000-0000-0000-0000-000000000000",
                workspace_id=self.workspace.id,
                user_id=self.user.id,
                content="hi",
            )
        )
        self.assertEqual([e.event for e in events], ["error"])
        mock_stream.assert_not_called()

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_missing_credential_yields_error_event(self, mock_stream):
        ProviderCredential.objects.all().delete()
        events = self._start_turn()
        self.assertEqual([e.event for e in events], ["error"])
        mock_stream.assert_not_called()


class SafeToolAutoExecuteTests(ChatOrchestratorTestBase):
    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_safe_tool_auto_executes_then_gets_followup_response(self, mock_stream):
        mock_stream.side_effect = [
            _stream(
                _tool_call_chunk("call_1", "web_search", '{"query": "agentarium"}'),
                _finish_chunk("tool_calls"),
            ),
            _stream(_content_chunk("Here's what I found."), _finish_chunk("stop")),
        ]
        events = self._start_turn("search for agentarium")
        event_types = [e.event for e in events]
        self.assertEqual(
            event_types, ["tool_call_started", "tool_call_result", "token", "message_complete"]
        )
        self.assertFalse(ApprovalRequest.objects.exists())
        self.assertEqual(mock_stream.call_count, 2)

        tool_message = Message.objects.get(tool_calls__isnull=False)
        self.assertEqual(tool_message.status, Message.Status.COMPLETE)
        result_message = Message.objects.get(parent_message=tool_message)
        self.assertEqual(result_message.tool_call_id, "call_1")
        self.assertEqual(result_message.sender_type, Message.SenderType.SYSTEM)

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_unattached_tool_records_error_without_crashing(self, mock_stream):
        mock_stream.side_effect = [
            _stream(
                _tool_call_chunk("call_1", "not_a_real_tool", "{}"), _finish_chunk("tool_calls")
            ),
            _stream(_content_chunk("Sorry, I can't do that."), _finish_chunk("stop")),
        ]
        events = self._start_turn()
        self.assertIn("tool_call_result", [e.event for e in events])
        result_message = Message.objects.get(tool_call_id="call_1")
        self.assertIn("error", json.loads(result_message.content))


class ApprovalGateTests(ChatOrchestratorTestBase):
    """SECURITY.md §4: `dangerous` tools can never auto-execute."""

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_dangerous_tool_blocks_for_approval_and_never_executes(self, mock_stream):
        mock_stream.return_value = _stream(
            _tool_call_chunk(
                "call_1", "execute_code", '{"language": "python", "code": "print(1)"}'
            ),
            _finish_chunk("tool_calls"),
        )
        events = self._start_turn("run some code")
        self.assertEqual([e.event for e in events], ["approval_required"])

        approval = ApprovalRequest.objects.get()
        self.assertEqual(approval.status, ApprovalRequest.Status.PENDING)
        self.assertEqual(approval.tool.name, "execute_code")
        self.assertEqual(approval.coworker_id, self.coworker.id)

        message = Message.objects.get(tool_calls__isnull=False)
        self.assertEqual(message.status, Message.Status.NEEDS_APPROVAL)
        # No tool-result exists because execution is blocked before the executor.
        self.assertFalse(Message.objects.filter(parent_message=message).exists())
        self.assertTrue(
            AuditLog.objects.filter(action="tool.approval_requested").exists()
        )
        self.assertFalse(AuditLog.objects.filter(action="tool.executed").exists())
        # setUp fails every non-streaming _post, so summary generation
        # degraded to blank — the gate itself must be unaffected.
        self.assertEqual(approval.summary, "")

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_gated_tool_gets_summary_and_rationale(self, mock_stream):
        """The approval_required event and the stored row both carry the
        model-generated headline plus the coworker's own preceding words."""
        mock_stream.return_value = _stream(
            _content_chunk("I need to run this to verify."),
            _tool_call_chunk("call_1", "execute_code", '{"code":"print(1)"}'),
            _finish_chunk("tool_calls"),
        )
        with patch.object(DeepSeekCloudAdapter, "_post") as mock_post:
            mock_post.return_value = {
                "model": "deepseek-v4-flash",
                "choices": [
                    {"message": {"content": "Run Python code: print(1)"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            }
            events = self._start_turn("run some code")

        approval_events = [e for e in events if e.event == "approval_required"]
        self.assertEqual(len(approval_events), 1)
        self.assertEqual(approval_events[0].data["summary"], "Run Python code: print(1)")
        self.assertEqual(approval_events[0].data["rationale"], "I need to run this to verify.")
        approval = ApprovalRequest.objects.get()
        self.assertEqual(approval.summary, "Run Python code: print(1)")
        self.assertEqual(approval.rationale, "I need to run this to verify.")
        self.assertEqual(approval.status, ApprovalRequest.Status.PENDING)
        self.assertFalse(AuditLog.objects.filter(action="tool.executed").exists())

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_approval_policy_auto_approves_under_threshold(self, mock_stream):
        """A standing "always allow under X" policy executes the gated tool
        without creating an approval request, and audits the standing
        consent that authorized it."""
        ApprovalPolicy.objects.create(
            workspace=self.workspace,
            coworker=self.coworker,
            tool=Tool.objects.get(name="execute_code"),
            argument_path="amount",
            max_amount=Decimal("250"),
        )
        mock_stream.side_effect = [
            _stream(
                _tool_call_chunk("call_1", "execute_code", '{"amount": 214.0}'),
                _finish_chunk("tool_calls"),
            ),
            _stream(_content_chunk("Done."), _finish_chunk("stop")),
        ]
        events = self._start_turn("refund the customers")
        names = [e.event for e in events]
        self.assertIn("tool_call_started", names)
        self.assertNotIn("approval_required", names)
        self.assertFalse(ApprovalRequest.objects.exists())
        self.assertTrue(AuditLog.objects.filter(action="tool.policy_auto_approved").exists())
        self.assertTrue(AuditLog.objects.filter(action="tool.executed").exists())

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_approval_policy_over_threshold_still_gates(self, mock_stream):
        """Fail-closed: an amount over the limit — or a missing argument —
        goes through the normal approval gate."""
        ApprovalPolicy.objects.create(
            workspace=self.workspace,
            coworker=self.coworker,
            tool=Tool.objects.get(name="execute_code"),
            argument_path="amount",
            max_amount=Decimal("250"),
        )
        mock_stream.return_value = _stream(
            _tool_call_chunk("call_1", "execute_code", '{"amount": 400.0}'),
            _finish_chunk("tool_calls"),
        )
        events = self._start_turn("refund the customers")
        self.assertEqual([e.event for e in events], ["approval_required"])
        self.assertEqual(ApprovalRequest.objects.get().status, ApprovalRequest.Status.PENDING)
        self.assertFalse(AuditLog.objects.filter(action="tool.executed").exists())

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_dangerous_tool_blocks_even_if_stored_policy_is_corrupted_to_auto(self, mock_stream):
        """Bypass-resistance: PermissionProfile.save() rejects dangerous->auto,
        but this proves the orchestrator doesn't rely on that write-path check —
        a row written around .save() (e.g. .update(), a future buggy migration)
        must still be refused at evaluation time."""
        PermissionProfile.objects.filter(id=self.permission_profile.id).update(
            default_tool_risk_policy={"safe": "auto", "sensitive": "auto", "dangerous": "auto"}
        )
        mock_stream.return_value = _stream(
            _tool_call_chunk("call_1", "execute_code", "{}"), _finish_chunk("tool_calls")
        )
        events = self._start_turn("run some code")
        self.assertEqual([e.event for e in events], ["approval_required"])
        self.assertEqual(ApprovalRequest.objects.get().status, ApprovalRequest.Status.PENDING)

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_resume_after_approval_executes_tool_and_continues(self, mock_stream):
        mock_stream.return_value = _stream(
            _tool_call_chunk("call_1", "execute_code", "{}"), _finish_chunk("tool_calls")
        )
        self._start_turn("run some code")
        approval = ApprovalRequest.objects.get()

        decide_approval_request(approval.id, approve=True, decided_by_user_id=self.user.id)
        self.assertEqual(
            ApprovalRequest.objects.get(id=approval.id).status, ApprovalRequest.Status.APPROVED
        )

        with patch.object(DeepSeekCloudAdapter, "_post_stream") as mock_stream2:
            mock_stream2.return_value = _stream(_content_chunk("Done."), _finish_chunk("stop"))
            events = self._resume_turn()

        self.assertEqual(
            [e.event for e in events],
            ["tool_call_started", "tool_call_result", "token", "message_complete"],
        )
        tool_message = Message.objects.get(tool_calls__isnull=False)
        self.assertEqual(tool_message.status, Message.Status.COMPLETE)
        result = Message.objects.get(parent_message=tool_message)
        # Empty arguments are rejected by the executor, but the result proves
        # it was reached only after approval.
        self.assertIn("error", json.loads(result.content))
        self.assertTrue(AuditLog.objects.filter(action="tool.executed").exists())

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_resume_after_denial_never_executes_and_continues(self, mock_stream):
        mock_stream.return_value = _stream(
            _tool_call_chunk("call_1", "execute_code", "{}"), _finish_chunk("tool_calls")
        )
        self._start_turn("run some code")
        approval = ApprovalRequest.objects.get()

        decide_approval_request(approval.id, approve=False, decided_by_user_id=self.user.id)

        with patch.object(DeepSeekCloudAdapter, "_post_stream") as mock_stream2:
            mock_stream2.return_value = _stream(
                _content_chunk("Understood, I won't run it."), _finish_chunk("stop")
            )
            events = self._resume_turn()

        self.assertEqual(
            [e.event for e in events],
            ["tool_call_result", "token", "message_complete"],
        )
        self.assertFalse(AuditLog.objects.filter(action="tool.executed").exists())
        tool_message = Message.objects.get(tool_calls__isnull=False)
        result = Message.objects.get(parent_message=tool_message)
        self.assertTrue(json.loads(result.content)["denied"])

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_resume_with_still_pending_approval_yields_nothing_new(self, mock_stream):
        mock_stream.return_value = _stream(
            _tool_call_chunk("call_1", "execute_code", "{}"), _finish_chunk("tool_calls")
        )
        self._start_turn("run some code")
        # No decision made yet.
        with patch.object(DeepSeekCloudAdapter, "_post_stream") as mock_stream2:
            events = self._resume_turn()
        self.assertEqual(events, [])
        mock_stream2.assert_not_called()

    def test_deciding_twice_raises(self):
        with patch.object(DeepSeekCloudAdapter, "_post_stream") as mock_stream:
            mock_stream.return_value = _stream(
                _tool_call_chunk("call_1", "execute_code", "{}"), _finish_chunk("tool_calls")
            )
            self._start_turn("run some code")
        approval = ApprovalRequest.objects.get()
        decide_approval_request(approval.id, approve=True, decided_by_user_id=self.user.id)
        from core.interface import ApprovalRequestAlreadyDecidedError

        with self.assertRaises(ApprovalRequestAlreadyDecidedError):
            decide_approval_request(approval.id, approve=True, decided_by_user_id=self.user.id)


class MaxIterationTests(ChatOrchestratorTestBase):
    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_runaway_auto_tool_loop_is_bounded(self, mock_stream):
        # web_search is "safe" -> auto-executes every time, so if nothing
        # bounded the loop this would spin forever.
        mock_stream.side_effect = lambda *_args, **_kwargs: _stream(
            _tool_call_chunk("call_x", "web_search", '{"query": "x"}'), _finish_chunk("tool_calls")
        )
        events = self._start_turn("infinite search")
        self.assertEqual(events[-1].event, "error")
        self.assertIn("maximum number of iterations", events[-1].data["detail"])


class ConcurrentToolExecutionRaceTests(TransactionTestCase):
    """Regression test for a check-then-act race that used to exist in tool
    call resolution: two concurrent resume_turn calls (a double-click, a
    client retry) could both pass the "not yet resolved" check before either
    stored a result, and both execute an approved tool call. Fixed with
    select_for_update row-locking (ai/chat_orchestrator.py
    _resolve_one_tool_call) plus a DB-level uniqueness constraint on
    (parent_message, tool_call_id) as defense-in-depth.

    Needs TransactionTestCase, not TestCase: select_for_update's row lock
    only serializes threads that see each other's *committed* writes across
    real, separate connections — TestCase's single wrapping transaction
    (never committed, rolled back at test end) would hide that entirely,
    the same class of bug Milestone 2 hit with cross-thread isolation."""

    def setUp(self):
        self.user = User.objects.create_user(email="race@example.com", password=VALID_PASSWORD)
        self.workspace = Workspace.objects.create(
            name="Race WS", type=Workspace.WorkspaceType.PERSONAL, owner=self.user
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace, user=self.user, role=WorkspaceMember.Role.OWNER
        )
        self.permission_profile = PermissionProfile.objects.create(
            workspace=self.workspace, name="Race Profile"
        )
        self.coworker = create_coworker(
            workspace=self.workspace, owner=self.user, created_by=self.user, name="Racer",
            role_description="test", model_binding={"primary": "deepseek-v4-flash"},
            permission_profile=self.permission_profile,
        )
        self.tool = Tool.objects.get(name="execute_code")
        CoworkerToolAttachment.objects.create(coworker=self.coworker, tool=self.tool, enabled=True)
        self.conversation = Conversation.objects.create(
            workspace=self.workspace, created_by=self.user, title="race"
        )
        self.assistant_message = Message.objects.create(
            conversation=self.conversation,
            sender_type=Message.SenderType.COWORKER,
            sender_id=self.coworker.id,
            content="",
            tool_calls=[{"id": "call_1", "name": "execute_code", "arguments": {"code": "print(1)"}}],
            status=Message.Status.NEEDS_APPROVAL,
        )
        approval = create_approval_request(
            coworker_id=self.coworker.id,
            tool_id=self.tool.id,
            requested_action={
                "tool_call_id": "call_1", "name": "execute_code", "arguments": {"code": "print(1)"}
            },
            conversation_id=self.conversation.id,
            message_id=self.assistant_message.id,
        )
        decide_approval_request(approval.id, approve=True, decided_by_user_id=self.user.id)

    def test_two_concurrent_resolutions_execute_the_tool_only_once(self):
        call_count = {"n": 0}
        call_lock = threading.Lock()

        def slow_execute_tool(*_args, **_kwargs):
            with call_lock:
                call_count["n"] += 1
            time.sleep(0.3)  # widen the race window so both threads overlap
            return ToolResult(output={"stdout": "", "stderr": ""})

        tools_by_name = {
            "execute_code": ToolInfo(
                id=self.tool.id, name="execute_code", description="",
                input_schema={}, risk_classification="dangerous",
            )
        }
        coworker_config = get_coworker_config(self.coworker.id)
        exceptions: list[BaseException] = []

        def run():
            try:
                list(
                    _advance_message_tool_calls(
                        conversation=self.conversation,
                        assistant_message=self.assistant_message,
                        tools_by_name=tools_by_name,
                        coworker_config=coworker_config,
                        workspace_id=self.workspace.id,
                        coworker_id=self.coworker.id,
                    )
                )
            except BaseException as exc:  # noqa: BLE001 — surfaced via assertion below
                exceptions.append(exc)
            finally:
                connection.close()

        with patch("ai.chat_orchestrator.execute_tool", side_effect=slow_execute_tool):
            threads = [threading.Thread(target=run) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(exceptions, [])
        self.assertEqual(
            call_count["n"], 1, "the tool executed more than once for a single approval"
        )
        result_messages = Message.objects.filter(
            parent_message=self.assistant_message, tool_call_id="call_1"
        )
        self.assertEqual(result_messages.count(), 1)
