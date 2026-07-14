from __future__ import annotations

import hmac
import re
from datetime import datetime, time, timedelta, timezone as dt_timezone
from decimal import Decimal

from django.conf import settings
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from ai.models import ModelCall
from core.interface import write_audit_log
from core.models import AuditLog, Coworker, User, WorkspaceMember
from core.permissions import get_workspace_for_member


def _admin_workspace(request: Request, workspace_id: str):
    workspace = get_workspace_for_member(request.user, workspace_id)
    membership = WorkspaceMember.objects.get(workspace=workspace, user=request.user)
    if membership.role not in (WorkspaceMember.Role.OWNER, WorkspaceMember.Role.ADMIN):
        raise PermissionDenied("Only workspace owners and admins can view observability data.")
    return workspace


def _parse_boundary(value: str | None, *, end: bool = False):
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is not None:
        return parsed
    day = parse_date(value)
    if day is not None:
        boundary = datetime.combine(day, time.min, tzinfo=dt_timezone.utc)
        return boundary + timedelta(days=1) if end else boundary
    raise ValidationError("Date filters must be ISO-8601 dates or datetimes.")


class AuditLogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, workspace_id: str) -> Response:
        workspace = _admin_workspace(request, workspace_id)
        queryset = AuditLog.objects.filter(workspace=workspace)
        start = _parse_boundary(request.query_params.get("from"))
        end = _parse_boundary(request.query_params.get("to"), end=True)
        if start:
            queryset = queryset.filter(created_at__gte=start)
        if end:
            queryset = queryset.filter(created_at__lt=end)
        if action := request.query_params.get("action"):
            queryset = queryset.filter(action__icontains=action)
        if resource_type := request.query_params.get("resource_type"):
            queryset = queryset.filter(resource_type=resource_type)
        if coworker_id := request.query_params.get("coworker_id"):
            queryset = queryset.filter(
                Q(actor_type=AuditLog.ActorType.COWORKER, actor_id=coworker_id)
                | Q(resource_type="coworker", resource_id=coworker_id)
                | Q(metadata__coworker_id=coworker_id)
            )
        try:
            offset = max(0, int(request.query_params.get("offset", "0")))
            limit = min(200, max(1, int(request.query_params.get("limit", "50"))))
        except ValueError as exc:
            raise ValidationError("offset and limit must be integers.") from exc
        count = queryset.count()
        rows = list(queryset.order_by("-created_at")[offset : offset + limit])
        users = dict(
            User.objects.filter(
                id__in=[row.actor_id for row in rows if row.actor_type == "user" and row.actor_id]
            ).values_list("id", "email")
        )
        coworkers = dict(
            Coworker.objects.filter(
                id__in=[
                    row.actor_id
                    for row in rows
                    if row.actor_type == "coworker" and row.actor_id
                ]
            ).values_list("id", "name")
        )
        return Response(
            {
                "count": count,
                "next_offset": offset + limit if offset + limit < count else None,
                "results": [
                    {
                        "id": str(row.id),
                        "actor_type": row.actor_type,
                        "actor_id": str(row.actor_id) if row.actor_id else None,
                        "actor_label": (
                            users.get(row.actor_id)
                            if row.actor_type == "user"
                            else coworkers.get(row.actor_id)
                            if row.actor_type == "coworker"
                            else "System"
                        ),
                        "action": row.action,
                        "resource_type": row.resource_type,
                        "resource_id": str(row.resource_id) if row.resource_id else None,
                        "metadata": row.metadata,
                        "created_at": row.created_at,
                    }
                    for row in rows
                ],
            }
        )


class UsageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, workspace_id: str) -> Response:
        workspace = _admin_workspace(request, workspace_id)
        range_value = request.query_params.get("range", "30d")
        match = re.fullmatch(r"(\d{1,3})d", range_value)
        if not match or not 1 <= int(match.group(1)) <= 365:
            raise ValidationError("range must be between 1d and 365d.")
        start = timezone.now() - timedelta(days=int(match.group(1)))
        calls = ModelCall.objects.filter(workspace=workspace, created_at__gte=start)
        cost_zero = Decimal("0.000000")
        totals = calls.aggregate(
            calls=Count("id"),
            input_tokens=Coalesce(Sum("input_tokens"), 0),
            output_tokens=Coalesce(Sum("output_tokens"), 0),
            cost_usd=Coalesce(Sum("cost_usd"), cost_zero),
            average_latency_ms=Coalesce(Avg("latency_ms"), 0.0),
        )
        by_coworker = list(
            calls.values("coworker_id", "coworker__name")
            .annotate(
                calls=Count("id"),
                input_tokens=Coalesce(Sum("input_tokens"), 0),
                output_tokens=Coalesce(Sum("output_tokens"), 0),
                cost_usd=Coalesce(Sum("cost_usd"), cost_zero),
            )
            .order_by("-cost_usd")
        )
        by_provider = list(
            calls.values("deployment_mode", "model_id")
            .annotate(
                calls=Count("id"),
                input_tokens=Coalesce(Sum("input_tokens"), 0),
                output_tokens=Coalesce(Sum("output_tokens"), 0),
                cost_usd=Coalesce(Sum("cost_usd"), cost_zero),
            )
            .order_by("-cost_usd")
        )
        daily = list(
            calls.annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(calls=Count("id"), cost_usd=Coalesce(Sum("cost_usd"), cost_zero))
            .order_by("date")
        )
        for item in by_coworker:
            item["coworker_id"] = str(item["coworker_id"]) if item["coworker_id"] else None
            item["coworker_name"] = item.pop("coworker__name") or "Unattributed"
        return Response(
            {
                "range": range_value,
                "from": start,
                "to": timezone.now(),
                "totals": totals,
                "by_coworker": by_coworker,
                "by_provider": by_provider,
                "daily": daily,
            }
        )


class InternalAuditSerializer(serializers.Serializer):
    workspace_id = serializers.UUIDField(required=False, allow_null=True)
    actor_type = serializers.ChoiceField(choices=AuditLog.ActorType.choices)
    actor_id = serializers.UUIDField(required=False, allow_null=True)
    action = serializers.CharField(max_length=255)
    resource_type = serializers.CharField(max_length=255)
    resource_id = serializers.UUIDField(required=False, allow_null=True)
    metadata = serializers.JSONField(required=False, default=dict)


class InternalAuditLogView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request: Request) -> Response:
        supplied = request.headers.get("X-Internal-Token", "")
        if not supplied or not hmac.compare_digest(supplied, settings.INTERNAL_API_TOKEN):
            raise PermissionDenied("Invalid internal service credential.")
        serializer = InternalAuditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        row = write_audit_log(
            actor_type=data["actor_type"],
            actor_id=data.get("actor_id"),
            action=data["action"],
            resource_type=data["resource_type"],
            resource_id=data.get("resource_id"),
            metadata=data.get("metadata"),
            workspace_id=data.get("workspace_id"),
        )
        return Response({"id": str(row.id), "created_at": row.created_at}, status=201)
