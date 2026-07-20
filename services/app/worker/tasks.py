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
    name="worker.execute_research_run",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
)
def execute_research_run(run_id: str) -> None:
    from research.services import execute_research_run as execute

    execute(run_id)


@app.task(name="worker.evaluate_due_website_monitors")
def evaluate_due_website_monitors() -> int:
    from research.services import evaluate_due_monitors

    return evaluate_due_monitors()


@app.task(
    name="worker.execute_website_monitor",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
)
def execute_website_monitor(self, check_id: str) -> None:
    from research.services import execute_monitor_run

    execute_monitor_run(
        check_id,
        final_attempt=self.request.retries >= self.max_retries,
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
        elif notification.type == Notification.Type.RESEARCH_COMPLETED:
            subject = f"Research completed: {title}"
            message = (
                f"Your research report '{title}' is ready.\n\n"
                f"View it: {settings.WEB_APP_URL}/research/{payload.get('research_run_id')}"
            )
        elif notification.type == Notification.Type.WEBSITE_CHANGED:
            subject = f"Website changed: {title}"
            message = (
                f"{payload.get('change_summary', 'A monitored website changed.')}.\n\n"
                f"View it: {settings.WEB_APP_URL}/research/monitors/"
                f"{payload.get('monitor_id')}"
            )
        elif notification.type == Notification.Type.MONITOR_FAILED:
            subject = f"Website monitor failed: {title}"
            message = (
                f"The monitor could not check {payload.get('url', 'the website')}.\n"
                f"{payload.get('error', '')}\n\n"
                f"Review it: {settings.WEB_APP_URL}/research/monitors/"
                f"{payload.get('monitor_id')}"
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


def enqueue_notification_deliveries(notification_id: str) -> None:
    """Queue each optional channel independently from the durable in-app row."""
    from django.conf import settings

    try:
        dispatch_notification_email.delay(notification_id)
    except Exception:
        pass
    if settings.TELEGRAM_ENABLED:
        try:
            dispatch_notification_telegram.delay(notification_id)
        except Exception:
            try:
                from core.models import TelegramDelivery

                TelegramDelivery.objects.update_or_create(
                    notification_id=notification_id,
                    defaults={
                        "status": TelegramDelivery.Status.FAILED,
                        "last_error": "enqueue_failed",
                    },
                )
            except Exception:
                # Never let an optional delivery channel change the source
                # task's outcome, even if the database is also unavailable.
                pass


def _telegram_preference_field(notification) -> str | None:
    from core.models import Notification

    if notification.type == Notification.Type.TASK_COMPLETED:
        return (
            "task_failed"
            if notification.payload.get("status") in {"failed", "blocked"}
            else "task_completed"
        )
    return {
        Notification.Type.RESEARCH_COMPLETED: "research_completed",
        Notification.Type.WEBSITE_CHANGED: "website_changed",
        Notification.Type.APPROVAL_REQUESTED: "approval_requested",
        Notification.Type.WORKFLOW_FAILED: "task_failed",
        Notification.Type.MONITOR_FAILED: "monitor_failed",
    }.get(notification.type)


def _telegram_notification_text(notification) -> str:
    from urllib.parse import quote

    from django.conf import settings

    from core.models import Notification

    payload = notification.payload
    title = " ".join(str(payload.get("title") or "Deep Foundry update").split())[:120]
    root = settings.WEB_APP_URL.rstrip("/")

    def internal_link(path: str, identifier=None) -> str:
        if identifier:
            return f"{root}{path}/{quote(str(identifier), safe='')}"
        return f"{root}{path}"

    if notification.type == Notification.Type.APPROVAL_REQUESTED:
        heading = "Approval required"
        link = internal_link("/approvals")
    elif notification.type == Notification.Type.RESEARCH_COMPLETED:
        heading = "Research completed"
        link = internal_link("/research", payload.get("research_run_id"))
    elif notification.type == Notification.Type.WEBSITE_CHANGED:
        heading = "Website changed"
        link = internal_link("/research/monitors", payload.get("monitor_id"))
    elif notification.type == Notification.Type.MONITOR_FAILED:
        heading = "Website monitor failed"
        link = internal_link("/research/monitors", payload.get("monitor_id"))
    elif notification.type == Notification.Type.WORKFLOW_FAILED:
        heading = "Workflow failed"
        link = internal_link("/workflows")
    elif payload.get("status") in {"failed", "blocked"}:
        heading = "Task needs attention"
        link = internal_link("/tasks", payload.get("task_id"))
    else:
        heading = "Task completed"
        link = internal_link("/tasks", payload.get("task_id"))
    return f"{heading}\n{title}\n\nOpen Deep Foundry: {link}"


@app.task(
    name="worker.dispatch_notification_telegram",
    bind=True,
    max_retries=5,
    acks_late=True,
    reject_on_worker_lost=True,
)
def dispatch_notification_telegram(self, notification_id: str) -> None:
    from datetime import timedelta

    from django.conf import settings
    from django.db import transaction
    from django.utils import timezone

    from core.models import (
        Notification,
        TelegramConnection,
        TelegramDelivery,
        TelegramNotificationPreference,
        WorkspaceMember,
    )
    from core.telegram import (
        TelegramPermanentError,
        TelegramRetryableError,
        send_telegram_message,
    )

    if not settings.TELEGRAM_ENABLED:
        return
    with transaction.atomic():
        notification = (
            Notification.objects.select_related("user", "workspace")
            .filter(id=notification_id)
            .first()
        )
        if notification is None:
            return
        delivery, _ = TelegramDelivery.objects.select_for_update().get_or_create(
            notification=notification
        )
        if delivery.status in (TelegramDelivery.Status.SENT, TelegramDelivery.Status.SKIPPED):
            return
        if (
            delivery.status == TelegramDelivery.Status.PROCESSING
            and delivery.updated_at > timezone.now() - timedelta(minutes=5)
        ):
            # Another worker owns a fresh lease, or this is a late-ack replay
            # after a worker crash. Retry after the lease can be reclaimed.
            raise self.retry(countdown=300)
        preference_field = _telegram_preference_field(notification)
        connection = TelegramConnection.objects.filter(
            user=notification.user, enabled=True
        ).first()
        preference = TelegramNotificationPreference.objects.filter(
            user=notification.user, workspace=notification.workspace, enabled=True
        ).first()
        still_authorized = (
            notification.user.is_active
            and WorkspaceMember.objects.filter(
                user=notification.user, workspace=notification.workspace
            ).exists()
        )
        if (
            preference_field is None
            or connection is None
            or preference is None
            or not getattr(preference, preference_field)
            or not still_authorized
        ):
            delivery.status = TelegramDelivery.Status.SKIPPED
            delivery.last_error = "not_enabled"
            delivery.save(update_fields=["status", "last_error", "updated_at"])
            return
        delivery.connection = connection
        delivery.status = TelegramDelivery.Status.PROCESSING
        delivery.attempts += 1
        delivery.last_error = ""
        delivery.save(
            update_fields=[
                "connection",
                "status",
                "attempts",
                "last_error",
                "updated_at",
            ]
        )

    try:
        external_id = send_telegram_message(
            connection.private_chat_id, _telegram_notification_text(notification)
        )
    except TelegramPermanentError:
        TelegramConnection.objects.filter(id=connection.id).update(enabled=False)
        TelegramDelivery.objects.filter(id=delivery.id).update(
            status=TelegramDelivery.Status.FAILED,
            last_error="destination_rejected",
        )
        return
    except TelegramRetryableError as exc:
        TelegramDelivery.objects.filter(id=delivery.id).update(
            status=TelegramDelivery.Status.FAILED,
            last_error=exc.code[:255],
        )
        if self.request.retries >= self.max_retries:
            return
        raise self.retry(
            exc=exc,
            countdown=exc.retry_after
            or min(2 ** (self.request.retries + 1), 60),
        )

    TelegramDelivery.objects.filter(id=delivery.id).update(
        status=TelegramDelivery.Status.SENT,
        external_message_id=external_id[:64],
        last_error="",
        sent_at=timezone.now(),
    )


@app.task(
    name="worker.dispatch_telegram_test",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def dispatch_telegram_test(user_id: str, workspace_id: str) -> None:
    from django.conf import settings

    from core.models import TelegramConnection, WorkspaceMember
    from core.telegram import TelegramPermanentError, send_telegram_message

    if not settings.TELEGRAM_ENABLED:
        return
    if not WorkspaceMember.objects.filter(user_id=user_id, workspace_id=workspace_id).exists():
        return
    connection = TelegramConnection.objects.filter(user_id=user_id, enabled=True).first()
    if connection is None:
        return
    try:
        send_telegram_message(
            connection.private_chat_id,
            f"Telegram notifications are working.\n\nOpen Deep Foundry: {settings.WEB_APP_URL.rstrip('/')}/home",
        )
    except TelegramPermanentError:
        TelegramConnection.objects.filter(id=connection.id).update(enabled=False)
