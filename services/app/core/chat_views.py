"""
Chat views, per API.md §4 and IMPLEMENTATION_PLAN.md Milestone 4.

Conversation/Message list/detail views read ai.models directly (see
ai/interface.py's docstring for why); sending a message, resuming a paused
turn, and regenerating a response go exclusively through ai.interface,
which is where the approval gate actually lives (SECURITY.md §4).
"""

import json

from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

import ai.interface as ai_interface
from ai.models import Conversation, ConversationParticipant, Message
from core.chat_serializers import (
    ConversationSerializer,
    MessagePatchSerializer,
    MessageSerializer,
    SendMessageSerializer,
)
from core.interface import (
    ApprovalRequestAlreadyDecidedError,
    ApprovalRequestNotFoundError,
    decide_approval_request,
    get_approval_request,
    write_audit_log,
)
from core.models import ApprovalRequest
from core.permissions import get_coworker_for_member, get_workspace_for_member
from core.serializers import ApprovalRequestSerializer


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _stream_events(events) -> StreamingHttpResponse:
    def generator():
        for chat_event in events:
            yield _sse(chat_event.event, chat_event.data)

    response = StreamingHttpResponse(generator(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    # Disable nginx-style proxy buffering, if one sits in front.
    response["X-Accel-Buffering"] = "no"
    return response


def _get_conversation_for_member(user, conversation_id: str) -> Conversation:
    conversation = get_object_or_404(Conversation, id=conversation_id)
    get_workspace_for_member(user, conversation.workspace_id)  # raises 403 if not a member
    return conversation


def _get_conversation_coworker_id(conversation: Conversation) -> str:
    participant = ConversationParticipant.objects.filter(
        conversation=conversation,
        participant_type=ConversationParticipant.ParticipantType.COWORKER,
    ).first()
    if participant is None:
        raise NotFound("This conversation has no coworker participant.")
    return participant.participant_id


class ConversationListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        workspace_id = request.query_params.get("workspace_id")
        if not workspace_id:
            raise ValidationError({"workspace_id": "This query parameter is required."})
        workspace = get_workspace_for_member(request.user, workspace_id)
        conversations = Conversation.objects.filter(workspace_id=workspace.id).order_by(
            "-created_at"
        )
        return Response(ConversationSerializer(conversations, many=True).data)

    def post(self, request: Request) -> Response:
        workspace_id = request.data.get("workspace_id")
        coworker_id = request.data.get("coworker_id")
        if not workspace_id or not coworker_id:
            raise ValidationError(
                {"workspace_id": "Required.", "coworker_id": "Required."}
            )
        workspace = get_workspace_for_member(request.user, workspace_id)
        coworker = get_coworker_for_member(request.user, coworker_id)
        if str(coworker.workspace_id) != str(workspace.id):
            raise ValidationError(
                {"coworker_id": "This coworker does not belong to that workspace."}
            )

        conversation = Conversation.objects.create(
            workspace=workspace, created_by=request.user, title=request.data.get("title", "")
        )
        ConversationParticipant.objects.create(
            conversation=conversation,
            participant_type=ConversationParticipant.ParticipantType.USER,
            participant_id=request.user.id,
        )
        ConversationParticipant.objects.create(
            conversation=conversation,
            participant_type=ConversationParticipant.ParticipantType.COWORKER,
            participant_id=coworker.id,
        )
        write_audit_log(
            actor_type="user", actor_id=request.user.id, action="conversation.create",
            resource_type="conversation", resource_id=conversation.id, workspace_id=workspace.id,
        )
        return Response(ConversationSerializer(conversation).data, status=status.HTTP_201_CREATED)


class ConversationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, conversation_id: str) -> Response:
        conversation = _get_conversation_for_member(request.user, conversation_id)
        return Response(ConversationSerializer(conversation).data)


class MessageListSendView(APIView):
    """GET lists messages; POST creates the user's message and streams the
    coworker's response inline on this same request (SSE), per API.md §4.
    One class handling both, per this codebase's established pattern for a
    list+create endpoint at one URL (e.g. CoworkerListCreateView) — two
    separate APIView classes can't share a path, only the first-registered
    one is ever reachable. The stream ends early if the turn blocks on an
    approval; GET .../messages/stream is how the client picks it back up."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, conversation_id: str) -> Response:
        conversation = _get_conversation_for_member(request.user, conversation_id)
        messages = conversation.messages.order_by("created_at")
        return Response(MessageSerializer(messages, many=True).data)

    def post(self, request: Request, conversation_id: str) -> StreamingHttpResponse:
        conversation = _get_conversation_for_member(request.user, conversation_id)
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        coworker_id = _get_conversation_coworker_id(conversation)

        events = ai_interface.start_turn(
            conversation_id=conversation.id,
            coworker_id=coworker_id,
            workspace_id=conversation.workspace_id,
            user_id=request.user.id,
            content=serializer.validated_data["content"],
        )
        return _stream_events(events)


class MessageStreamView(APIView):
    """GET /conversations/{id}/messages/stream — resumes a turn that's
    currently blocked on an approval decision, once one has been made."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, conversation_id: str) -> StreamingHttpResponse:
        conversation = _get_conversation_for_member(request.user, conversation_id)
        coworker_id = _get_conversation_coworker_id(conversation)
        events = ai_interface.resume_turn(
            conversation_id=conversation.id,
            coworker_id=coworker_id,
            workspace_id=conversation.workspace_id,
        )
        return _stream_events(events)


class MessageRegenerateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, message_id: str) -> StreamingHttpResponse:
        target = get_object_or_404(Message, id=message_id)
        conversation = _get_conversation_for_member(request.user, target.conversation_id)
        is_complete_coworker_message = (
            target.sender_type == Message.SenderType.COWORKER
            and target.status == Message.Status.COMPLETE
        )
        if not is_complete_coworker_message:
            raise ValidationError("Only a completed coworker message can be regenerated.")
        coworker_id = _get_conversation_coworker_id(conversation)

        events = ai_interface.regenerate_turn(
            conversation_id=conversation.id,
            coworker_id=coworker_id,
            workspace_id=conversation.workspace_id,
            target_message_id=target.id,
        )
        return _stream_events(events)


class MessagePatchView(APIView):
    """PATCH /messages/{id} — edits a user-authored message's content
    in place. No reprocessing: editing doesn't retroactively re-run the
    turn it was part of (that's what regenerate is for, on the coworker
    side)."""

    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, message_id: str) -> Response:
        target = get_object_or_404(Message, id=message_id)
        _get_conversation_for_member(request.user, target.conversation_id)
        if target.sender_type != Message.SenderType.USER or str(target.sender_id) != str(
            request.user.id
        ):
            raise PermissionDenied("You can only edit your own messages.")
        serializer = MessagePatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target.content = serializer.validated_data["content"]
        target.save(update_fields=["content"])
        return Response(MessageSerializer(target).data)


class ApprovalRequestListView(generics.ListAPIView):
    """GET /workspaces/{workspace_id}/approval-requests?status=pending —
    the approval inbox, per DATABASE.md §5's `(coworker_id, status)` index."""

    serializer_class = ApprovalRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        workspace = get_workspace_for_member(self.request.user, self.kwargs["workspace_id"])
        queryset = ApprovalRequest.objects.filter(coworker__workspace=workspace).select_related(
            "tool"
        )
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset.order_by("-created_at")


def _decide_approval_request(
    request: Request, approval_request_id: str, *, approve: bool
) -> Response:
    try:
        approval = get_approval_request(approval_request_id)
    except ApprovalRequestNotFoundError as exc:
        raise NotFound(str(exc)) from exc

    # Any member of the coworker's workspace may decide — SECURITY.md §4
    # leaves "who specifically can grant approval" as a later, configurable
    # refinement; this is the MVP default.
    coworker = get_coworker_for_member(request.user, approval.coworker_id)

    try:
        decided = decide_approval_request(
            approval_request_id, approve=approve, decided_by_user_id=request.user.id
        )
    except ApprovalRequestAlreadyDecidedError as exc:
        raise ValidationError(str(exc)) from exc

    write_audit_log(
        actor_type="user", actor_id=request.user.id,
        action="approval_request.approved" if approve else "approval_request.denied",
        resource_type="approval_request", resource_id=approval_request_id,
        workspace_id=coworker.workspace_id,
        metadata={"tool_id": str(decided.tool_id)},
    )
    decided_row = ApprovalRequest.objects.get(id=approval_request_id)
    if decided.task_id:
        from worker.tasks import execute_background_task

        execute_background_task.delay(str(decided.task_id))
    if decided.workflow_run_step_id:
        from core.models import WorkflowRun, WorkflowRunStep
        from worker.tasks import execute_workflow_run

        step = WorkflowRunStep.objects.select_related("workflow_run").get(
            id=decided.workflow_run_step_id
        )
        step.status = (
            WorkflowRunStep.Status.IN_PROGRESS
            if approve
            else WorkflowRunStep.Status.FAILED
        )
        step.save(update_fields=["status"])
        step.workflow_run.status = (
            WorkflowRun.Status.RUNNING
            if approve
            else WorkflowRun.Status.FAILED
        )
        update_fields = ["status"]
        if not approve:
            step.completed_at = timezone.now()
            step.save(update_fields=["status", "completed_at"])
            step.workflow_run.completed_at = timezone.now()
            update_fields.append("completed_at")
        step.workflow_run.save(update_fields=update_fields)
        if approve:
            execute_workflow_run.delay(str(step.workflow_run_id))
    return Response(ApprovalRequestSerializer(decided_row).data)


class ApprovalRequestApproveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, approval_request_id: str) -> Response:
        return _decide_approval_request(request, approval_request_id, approve=True)


class ApprovalRequestDenyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, approval_request_id: str) -> Response:
        return _decide_approval_request(request, approval_request_id, approve=False)
