from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from ai.models import Conversation, ConversationParticipant, Message
from core.interface import decide_approval_request, write_audit_log
from core.models import ApprovalRequest, Coworker, Notification, Task
from core.permissions import get_coworker_for_member, get_workspace_for_member
from worker.tasks import execute_background_task


class TaskSerializer(serializers.ModelSerializer):
    coworker_name = serializers.CharField(source="coworker.name", read_only=True)

    class Meta:
        model = Task
        fields = [
            "id", "workspace_id", "project_id", "coworker_id", "coworker_name",
            "created_by_type", "created_by_id", "title", "description", "status",
            "due_at", "parent_task_id", "result", "error_message", "created_at",
            "updated_at", "completed_at",
        ]
        read_only_fields = fields


class TaskCreateSerializer(serializers.Serializer):
    workspace_id = serializers.UUIDField()
    coworker_id = serializers.UUIDField()
    title = serializers.CharField(max_length=255)
    description = serializers.CharField()
    due_at = serializers.DateTimeField(required=False, allow_null=True)
    project_id = serializers.UUIDField(required=False, allow_null=True)


def _create_task(request: Request, data: dict) -> Task:
    workspace = get_workspace_for_member(request.user, data["workspace_id"])
    coworker = get_coworker_for_member(request.user, data["coworker_id"])
    if coworker.workspace_id != workspace.id or coworker.status != Coworker.Status.ACTIVE:
        raise ValidationError("The assignee must be an active coworker in this workspace.")
    with transaction.atomic():
        task = Task.objects.create(
            workspace=workspace, coworker=coworker,
            created_by_type=Task.CreatedByType.USER, created_by_id=request.user.id,
            title=data["title"], description=data["description"],
            due_at=data.get("due_at"), project_id=data.get("project_id"),
        )
        write_audit_log(
            actor_type="user", actor_id=request.user.id, action="task.create",
            resource_type="task", resource_id=task.id, workspace_id=workspace.id,
        )
        transaction.on_commit(lambda: execute_background_task.delay(str(task.id)))
    return task


class TaskListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        queryset = Task.objects.filter(
            workspace__members__user=request.user
        ).select_related("coworker").distinct()
        workspace_id = request.query_params.get("workspace_id")
        if workspace_id:
            get_workspace_for_member(request.user, workspace_id)
            queryset = queryset.filter(workspace_id=workspace_id)
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return Response(TaskSerializer(queryset, many=True).data)

    def post(self, request: Request) -> Response:
        serializer = TaskCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = _create_task(request, serializer.validated_data)
        return Response(TaskSerializer(task).data, status=status.HTTP_202_ACCEPTED)


class TaskDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, task_id: str) -> Response:
        task = get_object_or_404(Task.objects.select_related("coworker"), id=task_id)
        get_workspace_for_member(request.user, task.workspace_id)
        return Response(TaskSerializer(task).data)


class ConversationTaskHandoffView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, conversation_id: str) -> Response:
        conversation = get_object_or_404(Conversation, id=conversation_id)
        get_workspace_for_member(request.user, conversation.workspace_id)
        participant = get_object_or_404(
            ConversationParticipant,
            conversation=conversation,
            participant_type=ConversationParticipant.ParticipantType.COWORKER,
        )
        payload = request.data.copy()
        payload["workspace_id"] = conversation.workspace_id
        payload["coworker_id"] = participant.participant_id
        serializer = TaskCreateSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        task = _create_task(request, serializer.validated_data)
        return Response(TaskSerializer(task).data, status=status.HTTP_202_ACCEPTED)


class TaskDecisionView(APIView):
    permission_classes = [IsAuthenticated]
    approve = False

    def post(self, request: Request, task_id: str) -> Response:
        task = get_object_or_404(Task, id=task_id)
        get_workspace_for_member(request.user, task.workspace_id)
        approval = get_object_or_404(
            ApprovalRequest.objects.order_by("-created_at"),
            task_id=task.id,
            status=ApprovalRequest.Status.PENDING,
        )
        decide_approval_request(approval.id, approve=self.approve, decided_by_user_id=request.user.id)
        execute_background_task.delay(str(task.id))
        return Response({"task_id": str(task.id), "decision": "approved" if self.approve else "denied"})


class TaskApproveView(TaskDecisionView):
    approve = True


class TaskDenyView(TaskDecisionView):
    approve = False


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "workspace_id", "type", "payload", "read_at", "created_at"]
        read_only_fields = fields


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        queryset = Notification.objects.filter(user=request.user)
        if request.query_params.get("unread") == "true":
            queryset = queryset.filter(read_at__isnull=True)
        return Response(NotificationSerializer(queryset[:100], many=True).data)


class NotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, notification_id: str) -> Response:
        notification = get_object_or_404(Notification, id=notification_id, user=request.user)
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return Response(NotificationSerializer(notification).data)


# How long a blocked/failed task keeps coloring its coworker's status, and
# how long an in-flight streamed message counts as "working". Stale failures
# shouldn't paint a coworker red forever.
_STATUS_ATTENTION_WINDOW = timedelta(hours=24)
_STATUS_STREAMING_WINDOW = timedelta(minutes=10)


class CoworkerStatusListView(APIView):
    """GET /workspaces/{workspace_id}/coworkers/status — live status per
    coworker, fully derived: nothing is stored, so the status can never
    drift from the approvals, tasks, and messages that produce it.

    Precedence per coworker:
    needs_approval > blocked > error > working > idle.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, workspace_id: str) -> Response:
        workspace = get_workspace_for_member(request.user, workspace_id)
        now = timezone.now()
        coworkers = list(
            Coworker.objects.filter(
                workspace=workspace, status=Coworker.Status.ACTIVE
            ).values("id", "name")
        )
        coworker_ids = [row["id"] for row in coworkers]

        # Latest pending approval per coworker (iterated newest-first, so
        # the first one seen per coworker wins).
        pending_approval_by_coworker: dict = {}
        for approval in (
            ApprovalRequest.objects.filter(
                coworker_id__in=coworker_ids, status=ApprovalRequest.Status.PENDING
            )
            .select_related("tool")
            .order_by("-created_at")
        ):
            pending_approval_by_coworker.setdefault(
                approval.coworker_id,
                approval.summary or f"Wants to run {approval.tool.name}",
            )

        # Recent tasks, grouped per coworker into: active (running), needing
        # attention (blocked/failed recently), and last completed.
        active_by_coworker: dict = {}
        attention_by_coworker: dict = {}
        last_completed_by_coworker: dict = {}
        recent_tasks = Task.objects.filter(
            workspace=workspace, coworker_id__in=coworker_ids
        ).order_by("-updated_at")[:300]
        for task in recent_tasks:
            key = task.coworker_id
            if task.status in (Task.Status.PENDING, Task.Status.IN_PROGRESS):
                active_by_coworker.setdefault(key, task)
            elif (
                task.status in (Task.Status.BLOCKED, Task.Status.FAILED)
                and now - task.updated_at <= _STATUS_ATTENTION_WINDOW
            ):
                attention_by_coworker.setdefault(key, task)
            elif task.status == Task.Status.COMPLETED:
                last_completed_by_coworker.setdefault(key, task)

        # A coworker mid-stream in a conversation is working even with no
        # background task running.
        streaming_ids = set(
            Message.objects.filter(
                sender_type=Message.SenderType.COWORKER,
                sender_id__in=coworker_ids,
                status__in=(Message.Status.PENDING, Message.Status.STREAMING),
                created_at__gte=now - _STATUS_STREAMING_WINDOW,
            ).values_list("sender_id", flat=True)
        )

        payload = []
        for row in coworkers:
            coworker_id = row["id"]
            active = active_by_coworker.get(coworker_id)
            attention = attention_by_coworker.get(coworker_id)
            completed = last_completed_by_coworker.get(coworker_id)

            if coworker_id in pending_approval_by_coworker:
                state = "needs_approval"
                detail = pending_approval_by_coworker[coworker_id]
            elif attention is not None:
                state = "blocked" if attention.status == Task.Status.BLOCKED else "error"
                detail = attention.error_message or attention.title
            elif active is not None:
                state = "working"
                detail = active.title
            elif coworker_id in streaming_ids:
                state = "working"
                detail = "In a live conversation"
            else:
                state = "idle"
                detail = ""

            payload.append(
                {
                    "coworker_id": str(coworker_id),
                    "name": row["name"],
                    "state": state,
                    "detail": detail,
                    "last_run_at": completed.completed_at if completed else None,
                    "last_run_title": completed.title if completed else None,
                }
            )
        return Response(payload)
