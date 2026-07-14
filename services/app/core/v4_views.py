from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ai import interface as ai_interface
from core.models import (
    AgentTeam, CapabilityProposal, ConsensusSession, MemoryConflict,
    VoiceSession, VoiceTurn, WorkspaceMember,
)
from core.permissions import get_coworker_for_member, get_workspace_for_member
from core.v4_services import (
    create_capability_proposal, create_voice_session, detect_memory_conflicts,
    report_memory_conflict, resolve_memory_conflict, review_capability_proposal,
    start_consensus_session,
)


def _proposal_data(row: CapabilityProposal) -> dict:
    return {
        "id": str(row.id), "coworker_id": str(row.coworker_id),
        "coworker_name": row.coworker.name, "proposed_by_type": row.proposed_by_type,
        "target_type": row.target_type, "target_id": str(row.target_id),
        "target_name": row.target_name, "rationale": row.rationale,
        "status": row.status, "reviewed_by_id": str(row.reviewed_by_id) if row.reviewed_by_id else None,
        "reviewed_at": row.reviewed_at, "created_at": row.created_at,
    }


def _conflict_data(row: MemoryConflict) -> dict:
    return {
        "id": str(row.id), "subject": row.subject,
        "left_memory_id": str(row.left_memory_id), "right_memory_id": str(row.right_memory_id),
        "left_content": row.left_content, "right_content": row.right_content,
        "status": row.status, "resolution_strategy": row.resolution_strategy,
        "resolved_content": row.resolved_content, "resolved_at": row.resolved_at,
        "created_at": row.created_at,
    }


def _consensus_data(row: ConsensusSession) -> dict:
    return {
        "id": str(row.id), "agent_team_id": str(row.agent_team_id),
        "agent_team_name": row.agent_team.name, "question": row.question,
        "options": row.options, "method": row.method, "status": row.status,
        "result_option": row.result_option, "created_at": row.created_at,
        "completed_at": row.completed_at,
        "votes": [{
            "id": str(vote.id), "coworker_id": str(vote.coworker_id),
            "coworker_name": vote.coworker.name, "option": vote.option,
            "confidence": str(vote.confidence), "rationale": vote.rationale,
        } for vote in row.votes.select_related("coworker").all()],
    }


class CapabilityProposalListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id)
        rows = workspace.capability_proposals.select_related("coworker", "reviewed_by")
        status = request.query_params.get("status")
        if status:
            rows = rows.filter(status=status)
        return Response([_proposal_data(row) for row in rows])

    def post(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id)
        coworker = get_coworker_for_member(request.user, request.data.get("coworker_id"))
        if coworker.workspace_id != workspace.id:
            raise ValidationError({"coworker_id": "This coworker belongs to another workspace."})
        row = create_capability_proposal(
            coworker=coworker, target_type=request.data.get("target_type", ""),
            target_id=request.data.get("target_id"), rationale=request.data.get("rationale", ""),
            proposed_by_type=request.data.get("proposed_by_type", "coworker"),
        )
        return Response(_proposal_data(row), status=201)


class CapabilityProposalDecisionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, proposal_id):
        row = get_object_or_404(CapabilityProposal, id=proposal_id)
        get_workspace_for_member(request.user, row.workspace_id)
        decision = request.data.get("decision")
        if decision not in ("approve", "deny"):
            raise ValidationError({"decision": "Use approve or deny."})
        row = review_capability_proposal(row, user=request.user, approve=decision == "approve")
        return Response(_proposal_data(row))


class MemoryConflictListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id)
        if request.query_params.get("scan") == "true":
            detect_memory_conflicts(workspace)
        rows = workspace.memory_conflicts.all()
        status = request.query_params.get("status")
        if status:
            rows = rows.filter(status=status)
        return Response([_conflict_data(row) for row in rows])

    def post(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id)
        row = report_memory_conflict(
            workspace, left_memory_id=request.data.get("left_memory_id"),
            right_memory_id=request.data.get("right_memory_id"),
            subject=request.data.get("subject", ""),
        )
        return Response(_conflict_data(row), status=201)


class MemoryConflictResolveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conflict_id):
        row = get_object_or_404(MemoryConflict, id=conflict_id)
        get_workspace_for_member(request.user, row.workspace_id)
        row = resolve_memory_conflict(
            row, user=request.user, strategy=request.data.get("strategy", ""),
            merged_content=request.data.get("merged_content", ""),
        )
        return Response(_conflict_data(row))


class ConsensusSessionListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def _team(self, request, team_id):
        team = get_object_or_404(AgentTeam.objects.select_related("workspace", "current_version"), id=team_id)
        get_workspace_for_member(request.user, team.workspace_id)
        return team

    def get(self, request, team_id):
        team = self._team(request, team_id)
        rows = team.consensus_sessions.prefetch_related("votes__coworker")
        return Response([_consensus_data(row) for row in rows])

    def post(self, request, team_id):
        team = self._team(request, team_id)
        row = start_consensus_session(
            team, user=request.user, question=request.data.get("question", ""),
            options=request.data.get("options", []), method=request.data.get("method", "majority"),
        )
        return Response(_consensus_data(row), status=201)


class ConsensusSessionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        row = get_object_or_404(
            ConsensusSession.objects.select_related("agent_team__workspace").prefetch_related("votes__coworker"),
            id=session_id,
        )
        get_workspace_for_member(request.user, row.agent_team.workspace_id)
        return Response(_consensus_data(row))


def _voice_data(row: VoiceSession, *, include_turns=False) -> dict:
    data = {
        "id": str(row.id), "workspace_id": str(row.workspace_id),
        "coworker_id": str(row.coworker_id), "coworker_name": row.coworker.name,
        "conversation_id": str(row.conversation_id), "language": row.language,
        "status": row.status, "started_at": row.started_at, "ended_at": row.ended_at,
    }
    if include_turns:
        data["turns"] = [{
            "id": str(turn.id), "user_transcript": turn.user_transcript,
            "assistant_transcript": turn.assistant_transcript, "status": turn.status,
            "approval_request_id": str(turn.approval_request_id) if turn.approval_request_id else None,
            "error_message": turn.error_message, "created_at": turn.created_at,
        } for turn in row.turns.all()]
    return data


class VoiceSessionListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        workspace = get_workspace_for_member(request.user, request.query_params.get("workspace_id"))
        rows = workspace.voice_sessions.filter(user=request.user).select_related("coworker")[:50]
        return Response([_voice_data(row) for row in rows])

    def post(self, request):
        workspace = get_workspace_for_member(request.user, request.data.get("workspace_id"))
        coworker = get_coworker_for_member(request.user, request.data.get("coworker_id"))
        row = create_voice_session(
            workspace=workspace, coworker=coworker, user=request.user,
            language=request.data.get("language", "en-US"),
        )
        return Response(_voice_data(row), status=201)


class VoiceSessionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request, session_id):
        row = get_object_or_404(VoiceSession.objects.select_related("coworker"), id=session_id)
        get_workspace_for_member(request.user, row.workspace_id)
        if row.user_id != request.user.id:
            raise PermissionDenied("Voice sessions are private to their initiating user.")
        return row

    def get(self, request, session_id):
        return Response(_voice_data(self._get(request, session_id), include_turns=True))

    def patch(self, request, session_id):
        row = self._get(request, session_id)
        row.status = VoiceSession.Status.ENDED
        row.ended_at = timezone.now()
        row.save(update_fields=["status", "ended_at"])
        return Response(_voice_data(row))


class VoiceTurnCreateView(VoiceSessionDetailView):
    def post(self, request, session_id):
        session = self._get(request, session_id)
        if session.status != VoiceSession.Status.ACTIVE:
            raise ValidationError("This voice session has ended.")
        transcript = str(request.data.get("transcript", "")).strip()
        if not transcript:
            raise ValidationError({"transcript": "Speech transcript is required."})
        assistant = ""
        approval_id = None
        error = ""
        for event in ai_interface.start_turn(
            conversation_id=session.conversation_id, coworker_id=session.coworker_id,
            workspace_id=session.workspace_id, user_id=request.user.id, content=transcript,
        ):
            if event.event == "message_complete":
                assistant = event.data.get("content", assistant)
            elif event.event == "approval_required":
                approval_id = event.data.get("approval_request_id") or event.data.get("id")
            elif event.event == "error":
                error = event.data.get("detail", "Voice turn failed.")
        status = (
            VoiceTurn.Status.NEEDS_APPROVAL if approval_id else
            VoiceTurn.Status.FAILED if error else VoiceTurn.Status.COMPLETE
        )
        turn = VoiceTurn.objects.create(
            session=session, user_transcript=transcript, assistant_transcript=assistant,
            status=status, approval_request_id=approval_id, error_message=error,
        )
        return Response({
            "id": str(turn.id), "user_transcript": transcript,
            "assistant_transcript": assistant, "status": status,
            "approval_request_id": str(approval_id) if approval_id else None,
            "error_message": error,
        }, status=201)
