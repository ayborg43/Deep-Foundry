"""
Subscription plan limits: the single place that reads a workspace's plan and
decides whether it has room for one more coworker/agent team/task-this-month/
seat. Called from the same create paths regardless of what triggered them —
the manual UI, AI-designed team provisioning, and chat orchestration tools —
so no path can create past a limit.

The plan catalog itself (core.models.SubscriptionPlan) is edited only by
platform staff, via core.billing_views — see that module for the admin API.
"""

from __future__ import annotations

from typing import Literal

from django.utils import timezone

from core.models import (
    AgentTeam,
    AgentTeamRun,
    Coworker,
    Subscription,
    SubscriptionPlan,
    Task,
    Workspace,
    WorkspaceMember,
)

LimitKind = Literal["coworkers", "agent_teams", "tasks_per_month", "seats"]

_LIMIT_FIELD: dict[LimitKind, str] = {
    "coworkers": "max_coworkers",
    "agent_teams": "max_agent_teams",
    "tasks_per_month": "max_tasks_per_month",
    "seats": "max_seats",
}

_LIMIT_LABEL: dict[LimitKind, str] = {
    "coworkers": "coworkers",
    "agent_teams": "agent teams",
    "tasks_per_month": "tasks this month",
    "seats": "workspace members",
}


class PlanLimitExceeded(Exception):
    """Raised by the enforce_* functions below. Callers in DRF views catch
    this and respond 402 via plan_limit_response(); the orchestration tool
    executor catches it alongside OrchestrationError and surfaces it as a
    normal tool-call error the model (and therefore the chat user) can read."""

    def __init__(self, *, kind: LimitKind, limit: int, plan_name: str):
        self.kind = kind
        self.limit = limit
        self.plan_name = plan_name
        super().__init__(
            f"Your {plan_name} plan allows up to {limit} {_LIMIT_LABEL[kind]}. "
            "Upgrade your plan to add more."
        )


def default_plan() -> SubscriptionPlan | None:
    return (
        SubscriptionPlan.objects.filter(is_default=True, active=True).first()
        or SubscriptionPlan.objects.filter(active=True).order_by("sort_order", "price_usd").first()
    )


def get_active_plan(workspace: Workspace) -> SubscriptionPlan | None:
    """Self-healing: the first time anything asks, a workspace with no
    Subscription row yet (e.g. provisioned before billing existed) is put
    on the default plan rather than treated as unlimited."""
    subscription, _ = Subscription.objects.select_related("plan").get_or_create(
        workspace=workspace, defaults={"plan": default_plan()}
    )
    return subscription.plan


def get_usage(workspace: Workspace) -> dict[str, int]:
    """Current counts against each metered resource — for display (plan
    settings page) as well as internal checks."""
    return {
        "coworkers": Coworker.objects.filter(
            workspace=workspace, status=Coworker.Status.ACTIVE
        ).count(),
        "agent_teams": AgentTeam.objects.filter(workspace=workspace).count(),
        "tasks_per_month": _tasks_this_month(workspace),
        "seats": WorkspaceMember.objects.filter(workspace=workspace).count(),
    }


def _tasks_this_month(workspace: Workspace) -> int:
    start_of_month = timezone.now().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    manual = Task.objects.filter(
        workspace=workspace,
        created_by_type=Task.CreatedByType.USER,
        created_at__gte=start_of_month,
    ).count()
    # A team run counts once regardless of how many plan/delegate/synthesis
    # tasks it spawns internally — those are implementation detail, not a
    # separate user-initiated unit of work.
    runs = AgentTeamRun.objects.filter(
        agent_team__workspace=workspace, created_at__gte=start_of_month
    ).count()
    return manual + runs


def _check(workspace: Workspace, kind: LimitKind, current_count: int) -> None:
    plan = get_active_plan(workspace)
    if plan is None:
        return  # no catalog configured yet — nothing to enforce against
    limit = getattr(plan, _LIMIT_FIELD[kind])
    if limit is not None and current_count >= limit:
        raise PlanLimitExceeded(kind=kind, limit=limit, plan_name=plan.name)


def enforce_coworker_limit(workspace: Workspace) -> None:
    _check(
        workspace,
        "coworkers",
        Coworker.objects.filter(workspace=workspace, status=Coworker.Status.ACTIVE).count(),
    )


def enforce_agent_team_limit(workspace: Workspace) -> None:
    _check(workspace, "agent_teams", AgentTeam.objects.filter(workspace=workspace).count())


def enforce_seat_limit(workspace: Workspace) -> None:
    _check(workspace, "seats", WorkspaceMember.objects.filter(workspace=workspace).count())


def enforce_monthly_task_limit(workspace: Workspace) -> None:
    """Meters user-initiated units of work: a manually/chat-assigned task,
    or a team run's objective. Checked once, before anything is created, so
    a limit hit always fails cleanly rather than stopping a run partway
    through. Workflow-triggered tasks aren't metered here — they come from a
    recurring schedule the user already explicitly set up."""
    _check(workspace, "tasks_per_month", _tasks_this_month(workspace))


def plan_limit_response(exc: PlanLimitExceeded):
    from rest_framework.response import Response

    return Response(
        {
            "error": {
                "code": "plan_limit_reached",
                "message": str(exc),
                "details": {"kind": exc.kind, "limit": exc.limit, "plan": exc.plan_name},
            }
        },
        status=402,
    )
