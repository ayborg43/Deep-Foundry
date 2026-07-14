"""Durable Phase 2 Agent Team and Workflow execution state machines."""

from __future__ import annotations

from datetime import datetime

from django.db import transaction
from django.utils import timezone

from ai.interface import execute_workflow_tool
from core.interface import (
    create_approval_request,
    get_approval_request_for_workflow_step,
    get_coworker_config,
    notify_workspace,
    resolve_org_action_policy,
    write_audit_log,
)
from core.models import (
    AgentTeam,
    AgentTeamMember,
    AgentTeamRun,
    ApprovalRequest,
    CoworkerToolAttachment,
    Task,
    WorkflowRun,
    WorkflowRunStep,
    WorkflowTrigger,
)
from core.permissions import resolve_tool_permission


def _queue_task(task: Task) -> None:
    from worker.tasks import execute_background_task

    execute_background_task.delay(str(task.id))


def _team_task(run: AgentTeamRun, member: AgentTeamMember, title: str, description: str) -> Task:
    task = Task.objects.create(
        workspace=run.agent_team.workspace,
        coworker=member.coworker,
        created_by_type=Task.CreatedByType.COWORKER,
        created_by_id=run.id,
        title=title,
        description=description,
        execution_state={"agent_team_run_id": str(run.id), "team_role": member.role},
    )
    transaction.on_commit(lambda: _queue_task(task))
    return task


def advance_agent_team_run(run_id: str) -> bool:
    """Advance once; return True when the caller should poll again."""
    run = AgentTeamRun.objects.select_related("agent_team__workspace", "version").get(id=run_id)
    if run.status != AgentTeamRun.Status.RUNNING:
        return False
    members = list(run.version.members.select_related("coworker").all())
    tasks = list(Task.objects.filter(created_by_id=run.id).order_by("created_at"))
    if any(task.status == Task.Status.FAILED for task in tasks):
        run.status = AgentTeamRun.Status.FAILED
        run.result = "A team member task failed."
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "result", "completed_at"])
        return False
    if any(task.status not in (Task.Status.COMPLETED, Task.Status.FAILED, Task.Status.BLOCKED) for task in tasks):
        return True

    pattern = run.agent_team.collaboration_pattern
    if not tasks:
        if pattern == AgentTeam.CollaborationPattern.MANAGER_DELEGATE:
            manager = next(member for member in members if member.role == AgentTeamMember.Role.MANAGER)
            _team_task(run, manager, f"[plan] {run.objective[:180]}", f"Plan this team objective and define concrete work for delegates:\n{run.objective}")
        elif pattern == AgentTeam.CollaborationPattern.SEQUENTIAL:
            first = members[0]
            _team_task(run, first, run.objective[:255], run.objective)
        else:
            for member in members:
                _team_task(run, member, f"[{member.role}] {run.objective[:180]}", f"Contribute as {member.role} to this objective:\n{run.objective}")
        return True

    if pattern == AgentTeam.CollaborationPattern.MANAGER_DELEGATE:
        manager = next(member for member in members if member.role == AgentTeamMember.Role.MANAGER)
        plan = next((task for task in tasks if task.title.startswith("[plan]")), None)
        delegates = [task for task in tasks if task.title.startswith("[delegate:")]
        synthesis = next((task for task in tasks if task.title.startswith("[synthesis]")), None)
        if plan and not delegates and not synthesis:
            for member in members:
                if member.id == manager.id:
                    continue
                _team_task(
                    run, member, f"[delegate:{member.role}] {run.objective[:160]}",
                    f"Objective:\n{run.objective}\n\nManager plan:\n{plan.result}\n\nComplete the {member.role} contribution.",
                )
            if len(members) == 1:
                _team_task(run, manager, f"[synthesis] {run.objective[:180]}", f"Deliver the final result from this plan:\n{plan.result}")
            return True
        if delegates and not synthesis:
            contributions = "\n\n".join(f"{task.title}:\n{task.result}" for task in delegates)
            _team_task(run, manager, f"[synthesis] {run.objective[:180]}", f"Synthesize a final answer for:\n{run.objective}\n\nContributions:\n{contributions}")
            return True
        if synthesis:
            run.result = synthesis.result
    elif pattern == AgentTeam.CollaborationPattern.SEQUENTIAL:
        if len(tasks) < len(members):
            previous = tasks[-1]
            member = members[len(tasks)]
            _team_task(run, member, run.objective[:255], f"Continue this objective after the previous contribution:\n{run.objective}\n\nPrevious:\n{previous.result}")
            return True
        run.result = tasks[-1].result
    else:
        run.result = "\n\n".join(f"{task.title}\n{task.result}" for task in tasks)

    run.status = AgentTeamRun.Status.COMPLETED
    run.completed_at = timezone.now()
    run.save(update_fields=["status", "result", "completed_at"])
    write_audit_log(
        actor_type="system", actor_id=None, action="agent_team.completed",
        resource_type="agent_team_run", resource_id=run.id,
        workspace_id=run.agent_team.workspace_id,
    )
    return False


def advance_workflow_run(run_id: str) -> bool:
    """Advance one workflow until it blocks; return True when polling is needed."""
    run = WorkflowRun.objects.select_related("workflow_version__workflow__workspace").get(id=run_id)
    if run.status not in (WorkflowRun.Status.RUNNING, WorkflowRun.Status.NEEDS_APPROVAL):
        return False
    step = run.steps.filter(step_index=run.current_step_index).first()
    if step is None:
        run.status = WorkflowRun.Status.COMPLETED
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "completed_at"])
        return False
    if step.status == WorkflowRunStep.Status.NEEDS_APPROVAL:
        return False
    if step.status == WorkflowRunStep.Status.COMPLETED:
        run.current_step_index += 1
        run.save(update_fields=["current_step_index"])
        return advance_workflow_run(run_id)

    definition = step.definition
    workspace = run.workflow_version.workflow.workspace
    if step.step_type == WorkflowRunStep.StepType.CONDITION:
        condition = definition["condition"]
        value: object = run.context
        for key in str(condition["path"]).split("."):
            value = value.get(key) if isinstance(value, dict) else None
        operator = condition["operator"]
        expected = condition.get("value")
        if operator == "equals":
            matched = value == expected
        elif operator == "not_equals":
            matched = value != expected
        elif operator == "exists":
            matched = value is not None
        else:
            matched = expected in value if isinstance(value, (str, list, dict)) else False
        step.status = WorkflowRunStep.Status.COMPLETED
        step.result = {"matched": matched, "value": value}
        step.started_at = step.started_at or timezone.now()
        step.completed_at = timezone.now()
        step.save(update_fields=["status", "result", "started_at", "completed_at"])
        run.current_step_index = definition["if_true"] if matched else definition["if_false"]
        run.save(update_fields=["current_step_index"])
        return advance_workflow_run(run_id)
    if step.step_type == WorkflowRunStep.StepType.HUMAN_CHECKPOINT:
        step.status = WorkflowRunStep.Status.NEEDS_APPROVAL
        step.started_at = timezone.now()
        step.save(update_fields=["status", "started_at"])
        run.status = WorkflowRun.Status.NEEDS_APPROVAL
        run.save(update_fields=["status"])
        notify_workspace(
            workspace_id=workspace.id,
            notification_type="approval_requested",
            payload={"workflow_run_id": str(run.id), "workflow_step_id": str(step.id),
                     "title": definition.get("title", "Workflow checkpoint")},
        )
        return False

    if step.step_type == WorkflowRunStep.StepType.COWORKER_ACTION:
        task_id = (step.result or {}).get("task_id")
        if task_id:
            task = Task.objects.get(id=task_id)
            if task.status == Task.Status.COMPLETED:
                step.status = WorkflowRunStep.Status.COMPLETED
                step.result = {"task_id": str(task.id), "output": task.result}
                step.completed_at = timezone.now()
                step.save(update_fields=["status", "result", "completed_at"])
                run.current_step_index += 1
                run.save(update_fields=["current_step_index"])
                return advance_workflow_run(run_id)
            if task.status in (Task.Status.FAILED, Task.Status.BLOCKED):
                step.status = WorkflowRunStep.Status.FAILED
                step.result = {"task_id": str(task.id), "error": task.error_message}
                step.save(update_fields=["status", "result"])
                run.status = WorkflowRun.Status.FAILED
                run.completed_at = timezone.now()
                run.save(update_fields=["status", "completed_at"])
                return False
            return True
        task = Task.objects.create(
            workspace=workspace,
            coworker_id=definition["coworker_id"],
            created_by_type=Task.CreatedByType.WORKFLOW,
            created_by_id=run.id,
            title=definition.get("title", f"Workflow step {step.step_index + 1}"),
            description=definition.get("instructions") or definition.get("objective", "Complete this workflow step."),
            execution_state={"workflow_run_id": str(run.id), "workflow_run_step_id": str(step.id)},
        )
        step.status = WorkflowRunStep.Status.IN_PROGRESS
        step.started_at = timezone.now()
        step.result = {"task_id": str(task.id)}
        step.save(update_fields=["status", "started_at", "result"])
        transaction.on_commit(lambda: _queue_task(task))
        return True

    # Tool step
    attachment = CoworkerToolAttachment.objects.select_related("tool").get(
        coworker_id=definition["coworker_id"], tool__name=definition["tool_name"], enabled=True
    )
    config = get_coworker_config(definition["coworker_id"])
    approval = get_approval_request_for_workflow_step(step.id)
    org_decision = resolve_org_action_policy(
        workspace_id=workspace.id, resource_type="tool", action="execute",
        context={"tool_name": attachment.tool.name, "risk": attachment.tool.risk_classification},
    )
    if org_decision == "deny":
        step.status = WorkflowRunStep.Status.FAILED
        step.result = {"error": "Organization policy denied this tool action."}
        step.completed_at = timezone.now()
        step.save(update_fields=["status", "result", "completed_at"])
        run.status = WorkflowRun.Status.FAILED
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "completed_at"])
        return False
    decision = resolve_tool_permission(
        attachment.tool.risk_classification, config.permission_profile, config.org_policy_floor
    )
    if org_decision == "require_approval":
        decision = "approval"
    if decision == "approval" and approval is None:
        approval = create_approval_request(
            coworker_id=definition["coworker_id"], tool_id=attachment.tool_id,
            workflow_run_step_id=step.id,
            requested_action={"name": attachment.tool.name, "arguments": definition.get("arguments", {})},
        )
        step.status = WorkflowRunStep.Status.NEEDS_APPROVAL
        step.started_at = timezone.now()
        step.save(update_fields=["status", "started_at"])
        run.status = WorkflowRun.Status.NEEDS_APPROVAL
        run.save(update_fields=["status"])
        notify_workspace(
            workspace_id=workspace.id,
            notification_type="approval_requested",
            payload={"workflow_run_id": str(run.id), "approval_request_id": str(approval.id),
                     "title": definition.get("title", "Workflow tool approval")},
        )
        return False
    if approval and approval.status == ApprovalRequest.Status.PENDING:
        return False
    if approval and approval.status != ApprovalRequest.Status.APPROVED:
        run.status = WorkflowRun.Status.FAILED
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "completed_at"])
        return False
    output = execute_workflow_tool(
        attachment.tool.name, definition.get("arguments", {}), workspace_id=workspace.id
    )
    step.status = WorkflowRunStep.Status.COMPLETED if not output.error else WorkflowRunStep.Status.FAILED
    step.result = {**output.output, **({"error": output.error} if output.error else {})}
    step.completed_at = timezone.now()
    step.save(update_fields=["status", "result", "completed_at"])
    if output.error:
        run.status = WorkflowRun.Status.FAILED
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "completed_at"])
        return False
    run.current_step_index += 1
    run.save(update_fields=["current_step_index"])
    return advance_workflow_run(run_id)


def evaluate_due_triggers() -> int:
    from croniter import croniter

    from core.v2_services import start_workflow_run

    now = timezone.now()
    with transaction.atomic():
        due = list(
            WorkflowTrigger.objects.select_for_update()
            .select_related("workflow__current_version")
            .filter(
                trigger_type=WorkflowTrigger.TriggerType.SCHEDULED,
                enabled=True,
                next_run_at__lte=now,
            )
        )
        for trigger in due:
            start_workflow_run(trigger.workflow, triggered_by=WorkflowRun.TriggeredBy.SCHEDULE)
            trigger.next_run_at = croniter(trigger.schedule_cron, now).get_next(datetime)
            trigger.save(update_fields=["next_run_at"])
    return len(due)
