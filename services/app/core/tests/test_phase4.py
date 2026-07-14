from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from ai.memory import write_memory
from core.coworkers import create_coworker
from core.models import (
    CapabilityProposal, ConsensusSession, CoworkerToolAttachment,
    MemoryConflict, PermissionProfile, Task, Tool, User, VoiceSession,
    Workspace, WorkspaceMember,
)
from core.v2_services import create_agent_team
from core.v4_services import (
    detect_memory_conflicts, record_consensus_vote_from_task,
    resolve_memory_conflict, start_consensus_session,
)


class Phase4Base(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="phase4-owner@example.com", password="safe-test-password-123")
        self.workspace = Workspace.objects.create(name="Adaptive Lab", type="organization", owner=self.owner)
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        profile = PermissionProfile.objects.create(workspace=self.workspace, name="Default")
        self.alpha = create_coworker(workspace=self.workspace, owner=self.owner, name="Alpha", role_description="Decide carefully.", model_binding={"primary": "deepseek-chat"}, created_by=self.owner, permission_profile=profile)
        self.beta = create_coworker(workspace=self.workspace, owner=self.owner, name="Beta", role_description="Challenge assumptions.", model_binding={"primary": "deepseek-chat"}, created_by=self.owner, permission_profile=profile)
        self.client = APIClient(); self.client.force_authenticate(self.owner)


class CapabilityProposalTests(Phase4Base):
    def test_proposal_does_not_grant_until_human_approval(self):
        tool = Tool.objects.create(name="phase4_tool", description="Test", risk_classification="sensitive")
        response = self.client.post(f"/api/v1/workspaces/{self.workspace.id}/capability-proposals", {
            "coworker_id": str(self.alpha.id), "target_type": "tool",
            "target_id": str(tool.id), "rationale": "The task needs this tool.",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertFalse(CoworkerToolAttachment.objects.filter(coworker=self.alpha, tool=tool).exists())
        approved = self.client.post(f"/api/v1/capability-proposals/{response.data['id']}/decision", {"decision": "approve"}, format="json")
        self.assertEqual(approved.status_code, 200)
        self.assertTrue(CoworkerToolAttachment.objects.filter(coworker=self.alpha, tool=tool, enabled=True).exists())

    def test_member_cannot_approve_capability(self):
        member = User.objects.create_user(email="phase4-member@example.com", password="safe-test-password-123")
        WorkspaceMember.objects.create(workspace=self.workspace, user=member, role="member")
        tool = Tool.objects.create(name="phase4_admin_tool", description="Test", risk_classification="safe")
        proposal = CapabilityProposal.objects.create(workspace=self.workspace, coworker=self.alpha, target_type="tool", target_id=tool.id, target_name=tool.name, rationale="Need it")
        client = APIClient(); client.force_authenticate(member)
        response = client.post(f"/api/v1/capability-proposals/{proposal.id}/decision", {"decision": "approve"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(CoworkerToolAttachment.objects.filter(coworker=self.alpha, tool=tool).exists())


class MemoryConflictTests(Phase4Base):
    def test_detects_cross_coworker_subject_conflict_and_resolves_to_both_scopes(self):
        left = write_memory(workspace_id=self.workspace.id, scope="coworker", scope_id=self.alpha.id, content="launch date: 14 July")
        right = write_memory(workspace_id=self.workspace.id, scope="coworker", scope_id=self.beta.id, content="launch date: 21 July")
        detected = detect_memory_conflicts(self.workspace)
        self.assertEqual(len(detected), 1)
        conflict = detected[0]
        self.assertEqual({str(conflict.left_memory_id), str(conflict.right_memory_id)}, {str(left.id), str(right.id)})
        resolve_memory_conflict(conflict, user=self.owner, strategy="merge", merged_content="Launch after security sign-off.")
        conflict.refresh_from_db(); self.assertEqual(conflict.status, MemoryConflict.Status.RESOLVED)
        self.assertEqual(self.workspace.memory_entries.filter(source_ref_id=conflict.id).count(), 2)


class ConsensusTests(Phase4Base):
    def setUp(self):
        super().setUp()
        self.team = create_agent_team(workspace=self.workspace, user=self.owner, payload={
            "name": "Decision council", "collaboration_pattern": "parallel_merge",
            "members": [{"coworker_id": str(self.alpha.id), "role": "reviewer"}, {"coworker_id": str(self.beta.id), "role": "reviewer"}],
        })

    def test_majority_session_fans_out_tasks_and_records_auditable_votes(self):
        session = start_consensus_session(self.team, user=self.owner, question="Ship?", options=["Ship", "Wait"], method="majority")
        tasks = list(Task.objects.filter(execution_state__consensus_session_id=str(session.id)).order_by("id"))
        self.assertEqual(len(tasks), 2)
        for task in tasks:
            task.status = Task.Status.COMPLETED
            task.result = '{"option":"Ship","confidence":0.8,"rationale":"Checks passed"}'
            task.save(update_fields=["status", "result"])
            record_consensus_vote_from_task(task)
        session.refresh_from_db()
        self.assertEqual(session.status, ConsensusSession.Status.DECIDED)
        self.assertEqual(session.result_option, "Ship")
        self.assertEqual(session.votes.count(), 2)

    def test_unanimous_disagreement_is_deadlocked(self):
        session = start_consensus_session(self.team, user=self.owner, question="Ship?", options=["Ship", "Wait"], method="unanimous")
        tasks = list(Task.objects.filter(execution_state__consensus_session_id=str(session.id)).order_by("id"))
        for task, option in zip(tasks, ["Ship", "Wait"], strict=True):
            task.status = Task.Status.COMPLETED; task.result = f'{{"option":"{option}","confidence":1}}'; task.save(update_fields=["status", "result"])
            record_consensus_vote_from_task(task)
        session.refresh_from_db(); self.assertEqual(session.status, ConsensusSession.Status.DEADLOCKED)


class VoiceSessionTests(Phase4Base):
    @patch("core.v4_views.ai_interface.start_turn")
    def test_voice_turn_uses_existing_chat_pipeline_and_persists_transcript(self, start_turn):
        start_turn.return_value = iter([
            SimpleNamespace(event="token", data={"delta": "Hello"}),
            SimpleNamespace(event="message_complete", data={"content": "Hello from Alpha."}),
        ])
        created = self.client.post("/api/v1/voice-sessions", {
            "workspace_id": str(self.workspace.id), "coworker_id": str(self.alpha.id), "language": "en-US",
        }, format="json")
        self.assertEqual(created.status_code, 201)
        response = self.client.post(f"/api/v1/voice-sessions/{created.data['id']}/turns", {"transcript": "Hello Alpha"}, format="json")
        self.assertEqual(response.status_code, 201); self.assertEqual(response.data["assistant_transcript"], "Hello from Alpha.")
        session = VoiceSession.objects.get(id=created.data["id"])
        self.assertEqual(session.turns.get().user_transcript, "Hello Alpha")
        start_turn.assert_called_once()
