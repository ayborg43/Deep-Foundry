"""
Subscription plan catalog API.

- GET /plans — any authenticated user; the active catalog, for pricing and
  self-serve upgrade pickers (core.v2_views.SubscriptionView.patch is where a
  workspace actually switches plans).
- /admin/plans, /admin/plans/{id} — platform staff only (Django is_staff,
  via DRF's IsAdminUser). Create, edit, and retire plans. Nothing here
  touches any workspace's current subscription — editing a plan's limits
  takes effect for every workspace already on it the next time a limit is
  checked (core.billing reads the plan live, it isn't snapshotted).
"""

from __future__ import annotations

from django.db.models import ProtectedError
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.interface import write_audit_log
from core.models import SubscriptionPlan


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = [
            "id", "key", "name", "description", "price_usd",
            "max_coworkers", "max_agent_teams", "max_tasks_per_month", "max_seats",
            "is_default", "active", "sort_order", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PlanCatalogView(APIView):
    """GET /plans — the active plans any workspace member can choose from."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        plans = SubscriptionPlan.objects.filter(active=True)
        return Response(SubscriptionPlanSerializer(plans, many=True).data)


class PlanAdminListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request: Request) -> Response:
        plans = SubscriptionPlan.objects.all()
        return Response(SubscriptionPlanSerializer(plans, many=True).data)

    def post(self, request: Request) -> Response:
        serializer = SubscriptionPlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = serializer.save()
        write_audit_log(
            actor_type="user", actor_id=request.user.id, action="subscription_plan.create",
            resource_type="subscription_plan", resource_id=plan.id, workspace_id=None,
            metadata={"key": plan.key, "name": plan.name},
        )
        return Response(SubscriptionPlanSerializer(plan).data, status=status.HTTP_201_CREATED)


class PlanAdminDetailView(APIView):
    permission_classes = [IsAdminUser]

    def _get(self, plan_id: str) -> SubscriptionPlan:
        try:
            return SubscriptionPlan.objects.get(id=plan_id)
        except (SubscriptionPlan.DoesNotExist, ValueError, TypeError) as exc:
            raise ValidationError({"plan_id": "No plan with that id."}) from exc

    def get(self, request: Request, plan_id: str) -> Response:
        return Response(SubscriptionPlanSerializer(self._get(plan_id)).data)

    def patch(self, request: Request, plan_id: str) -> Response:
        plan = self._get(plan_id)
        serializer = SubscriptionPlanSerializer(plan, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        plan = serializer.save()
        write_audit_log(
            actor_type="user", actor_id=request.user.id, action="subscription_plan.update",
            resource_type="subscription_plan", resource_id=plan.id, workspace_id=None,
            metadata={"key": plan.key, "changed": list(request.data.keys())},
        )
        return Response(SubscriptionPlanSerializer(plan).data)

    def delete(self, request: Request, plan_id: str) -> Response:
        plan = self._get(plan_id)
        try:
            plan.delete()
        except ProtectedError:
            raise ValidationError(
                {"plan_id": "This plan has active subscriptions — deactivate it instead of deleting."}
            )
        write_audit_log(
            actor_type="user", actor_id=request.user.id, action="subscription_plan.delete",
            resource_type="subscription_plan", resource_id=plan_id, workspace_id=None,
            metadata={"key": plan.key},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
