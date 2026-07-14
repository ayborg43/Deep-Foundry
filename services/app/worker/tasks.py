"""
Milestone 0 no-op task: proves the worker entrypoint boots against the same
codebase as the ASGI app and can import Core and AI modules directly, in
process, per ARCHITECTURE.md §3.2 (no network hop between worker and app).
"""

from ai.main import app as ai_app  # noqa: F401  (import-only proof, per Epic 0.1)
from config.celery import app


@app.task(name="worker.ping")
def ping() -> str:
    return "pong"


@app.task(name="worker.ingest_knowledge_document", autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def ingest_knowledge_document(document_id: str) -> None:
    from ai.knowledge import ingest_document

    ingest_document(document_id)


@app.task(name="worker.execute_background_task")
def execute_background_task(task_id: str) -> None:
    from ai.task_engine import execute_background_task as execute
    from core.models import Task

    execute(task_id)
    task = Task.objects.filter(id=task_id).first()
    if task and task.execution_state.get("consensus_session_id"):
        from core.v4_services import record_consensus_vote_from_task

        record_consensus_vote_from_task(task)
    if task and task.execution_state.get("workflow_run_id"):
        execute_workflow_run.delay(task.execution_state["workflow_run_id"])
    if task and task.execution_state.get("agent_team_run_id"):
        execute_agent_team_run.delay(task.execution_state["agent_team_run_id"])


@app.task(name="worker.execute_workflow_run", bind=True, max_retries=None)
def execute_workflow_run(self, run_id: str) -> None:
    from core.v2_engine import advance_workflow_run

    if advance_workflow_run(run_id):
        self.apply_async(args=[run_id], countdown=5)


@app.task(name="worker.execute_agent_team_run", bind=True, max_retries=None)
def execute_agent_team_run(self, run_id: str) -> None:
    from core.v2_engine import advance_agent_team_run

    if advance_agent_team_run(run_id):
        self.apply_async(args=[run_id], countdown=5)


@app.task(name="worker.evaluate_scheduled_workflows")
def evaluate_scheduled_workflows() -> int:
    from core.v2_engine import evaluate_due_triggers

    return evaluate_due_triggers()


@app.task(name="worker.detect_audit_anomalies")
def detect_audit_anomalies_task() -> int:
    from core.models import Workspace
    from core.v3_services import detect_audit_anomalies

    return sum(
        len(detect_audit_anomalies(workspace))
        for workspace in Workspace.objects.filter(type=Workspace.WorkspaceType.ORGANIZATION)
    )


@app.task(
    name="worker.dispatch_notification_email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=5,
)
def dispatch_notification_email(notification_id: str) -> None:
    from django.conf import settings
    from django.core.mail import send_mail
    from django.db import transaction
    from django.utils import timezone

    from core.models import Notification

    with transaction.atomic():
        notification = Notification.objects.select_for_update().select_related("user").get(
            id=notification_id
        )
        if notification.email_sent_at is not None:
            return
        payload = notification.payload
        title = payload.get("title", "Background task")
        task_id = payload.get("task_id")
        if notification.type == Notification.Type.APPROVAL_REQUESTED:
            subject = f"Approval required: {title}"
            message = (
                f"A coworker needs approval to call {payload.get('tool_name', 'a tool')} "
                f"while working on {title}.\n\n"
                f"Review it: {settings.WEB_APP_URL}/approvals"
            )
        else:
            subject = f"Task {payload.get('status', 'updated')}: {title}"
            message = (
                f"Your background task '{title}' is {payload.get('status', 'updated')}.\n\n"
                f"View it: {settings.WEB_APP_URL}/tasks/{task_id}"
            )
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [notification.user.email],
            fail_silently=False,
        )
        notification.email_sent_at = timezone.now()
        notification.save(update_fields=["email_sent_at"])
