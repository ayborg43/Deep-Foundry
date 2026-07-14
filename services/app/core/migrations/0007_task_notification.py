import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0006_alter_auditlog_workspace")]

    operations = [
        migrations.CreateModel(
            name="Task",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("project_id", models.UUIDField(blank=True, null=True)),
                ("created_by_type", models.CharField(choices=[("user", "User"), ("coworker", "Coworker"), ("workflow", "Workflow")], max_length=20)),
                ("created_by_id", models.UUIDField()),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField()),
                ("status", models.CharField(choices=[("pending", "Pending"), ("in_progress", "In progress"), ("needs_approval", "Needs approval"), ("blocked", "Blocked"), ("completed", "Completed"), ("failed", "Failed")], default="pending", max_length=20)),
                ("due_at", models.DateTimeField(blank=True, null=True)),
                ("execution_state", models.JSONField(blank=True, default=dict)),
                ("result", models.TextField(blank=True)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("coworker", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tasks", to="core.coworker")),
                ("parent_task", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="subtasks", to="core.task")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tasks", to="core.workspace")),
            ],
            options={"db_table": "tasks", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("type", models.CharField(choices=[("task_completed", "Task completed"), ("approval_requested", "Approval requested"), ("workflow_failed", "Workflow failed"), ("mention", "Mention"), ("billing", "Billing")], max_length=30)),
                ("payload", models.JSONField(default=dict)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("email_sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to=settings.AUTH_USER_MODEL)),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="core.workspace")),
            ],
            options={"db_table": "notifications", "ordering": ["-created_at"]},
        ),
        migrations.AddIndex(model_name="task", index=models.Index(fields=["workspace", "status"], name="tasks_workspac_47cb9b_idx")),
        migrations.AddIndex(model_name="notification", index=models.Index(fields=["user", "read_at", "created_at"], name="notificatio_user_id_ee8d09_idx")),
    ]
