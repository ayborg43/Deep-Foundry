import json
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from celery.exceptions import Retry
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    AuditLog,
    Notification,
    TelegramConnection,
    TelegramDelivery,
    TelegramLinkSession,
    TelegramNotificationPreference,
    User,
    Workspace,
    WorkspaceMember,
)
from core.telegram import TelegramPermanentError
from worker.tasks import (
    dispatch_notification_telegram,
    enqueue_notification_deliveries,
)

TELEGRAM_SETTINGS = {
    "TELEGRAM_ENABLED": True,
    "TELEGRAM_BOT_TOKEN": "123456:test-token",
    "TELEGRAM_BOT_USERNAME": "DeepFoundryTestBot",
    "TELEGRAM_WEBHOOK_SECRET": "test-webhook-secret-that-is-long-enough",
    "TELEGRAM_LINK_TTL_SECONDS": 600,
    "TELEGRAM_WEBHOOK_MAX_BYTES": 65536,
}


@override_settings(**TELEGRAM_SETTINGS)
class TelegramApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="telegram@example.com", password="correct horse battery staple"
        )
        self.workspace = Workspace.objects.create(
            name="Telegram", type=Workspace.WorkspaceType.PERSONAL, owner=self.user
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.user,
            role=WorkspaceMember.Role.OWNER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _create_link(self, client=None):
        response = (client or self.client).post(
            "/api/v1/telegram/link-sessions",
            {"workspace_id": str(self.workspace.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        token = parse_qs(urlsplit(response.data["deep_link_url"]).query)["start"][0]
        return response, token

    def _webhook(self, token, *, telegram_id=987654321, chat_type="private", secret=None):
        body = json.dumps(
            {
                "update_id": 100,
                "message": {
                    "message_id": 10,
                    "text": f"/start {token}",
                    "from": {
                        "id": telegram_id,
                        "first_name": "Ada",
                        "last_name": "Lovelace",
                        "username": "ada_l",
                    },
                    "chat": {"id": telegram_id, "type": chat_type},
                },
            }
        )
        return APIClient().generic(
            "POST",
            "/api/v1/webhooks/telegram",
            body,
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=secret
            or TELEGRAM_SETTINGS["TELEGRAM_WEBHOOK_SECRET"],
        )

    def test_link_token_is_hashed_and_private_webhook_binds_owner_once(self):
        response, token = self._create_link()
        link_session = TelegramLinkSession.objects.get(id=response.data["id"])
        self.assertNotEqual(link_session.token_hash, token)
        self.assertNotIn(token, link_session.token_hash)

        webhook = self._webhook(token)
        self.assertEqual(webhook.status_code, 200)
        self.assertEqual(webhook.data["method"], "sendMessage")
        connection = TelegramConnection.objects.get(user=self.user)
        self.assertEqual(connection.telegram_user_id, 987654321)
        self.assertEqual(connection.private_chat_id, 987654321)
        self.assertEqual(connection.username, "ada_l")
        self.assertTrue(
            TelegramNotificationPreference.objects.filter(
                user=self.user, workspace=self.workspace
            ).exists()
        )
        link_session.refresh_from_db()
        self.assertIsNotNone(link_session.used_at)
        status_response = self.client.get(
            f"/api/v1/telegram/link-sessions/{link_session.id}"
        )
        self.assertEqual(status_response.data["status"], "linked")
        self.assertTrue(
            AuditLog.objects.filter(
                actor_id=self.user.id, action="telegram.connected"
            ).exists()
        )

        replay = self._webhook(token)
        self.assertEqual(replay.status_code, 200)
        self.assertIn("invalid or expired", replay.data["text"])
        self.assertEqual(TelegramConnection.objects.count(), 1)

    def test_webhook_rejects_bad_secret_and_ignores_group_chat(self):
        response, token = self._create_link()
        denied = self._webhook(token, secret="wrong")
        self.assertEqual(denied.status_code, 403)
        ignored = self._webhook(token, chat_type="group")
        self.assertEqual(ignored.status_code, 200)
        self.assertFalse(TelegramConnection.objects.exists())
        self.assertEqual(
            self.client.get(
                f"/api/v1/telegram/link-sessions/{response.data['id']}"
            ).data["status"],
            "pending",
        )

    def test_new_link_cancels_previous_session_and_webhook_rejects_bad_shapes(self):
        first, _ = self._create_link()
        second, _ = self._create_link()
        self.assertEqual(
            self.client.get(
                f"/api/v1/telegram/link-sessions/{first.data['id']}"
            ).data["status"],
            "cancelled",
        )
        self.assertEqual(
            self.client.get(
                f"/api/v1/telegram/link-sessions/{second.data['id']}"
            ).data["status"],
            "pending",
        )
        webhook_client = APIClient()
        headers = {
            "HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": TELEGRAM_SETTINGS[
                "TELEGRAM_WEBHOOK_SECRET"
            ]
        }
        non_object = webhook_client.generic(
            "POST",
            "/api/v1/webhooks/telegram",
            "[]",
            content_type="application/json",
            **headers,
        )
        self.assertEqual(non_object.status_code, 400)
        oversized = webhook_client.generic(
            "POST",
            "/api/v1/webhooks/telegram",
            json.dumps({"padding": "x" * 66000}),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(oversized.status_code, 413)

    @patch(
        "core.telegram_views.TelegramConnection.objects.create",
        side_effect=IntegrityError("unique race"),
    )
    def test_webhook_uniqueness_race_returns_neutral_collision(self, _create):
        response, token = self._create_link()
        webhook = self._webhook(token)
        self.assertEqual(webhook.status_code, 200)
        self.assertIn("already connected", webhook.data["text"])
        self.assertEqual(
            self.client.get(
                f"/api/v1/telegram/link-sessions/{response.data['id']}"
            ).data["status"],
            "cancelled",
        )

    def test_expired_token_and_cross_user_account_collision_cannot_link(self):
        _, first_token = self._create_link()
        self.assertEqual(self._webhook(first_token, telegram_id=42).status_code, 200)

        second_user = User.objects.create_user(
            email="other@example.com", password="correct horse battery staple"
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=second_user,
            role=WorkspaceMember.Role.MEMBER,
        )
        second_client = APIClient()
        second_client.force_authenticate(second_user)
        second_response = second_client.post(
            "/api/v1/telegram/link-sessions",
            {"workspace_id": str(self.workspace.id)},
            format="json",
        )
        second_token = parse_qs(
            urlsplit(second_response.data["deep_link_url"]).query
        )["start"][0]
        collision = self._webhook(second_token, telegram_id=42)
        self.assertIn("already connected", collision.data["text"])
        self.assertFalse(TelegramConnection.objects.filter(user=second_user).exists())

        third_response = second_client.post(
            "/api/v1/telegram/link-sessions",
            {"workspace_id": str(self.workspace.id)},
            format="json",
        )
        third_token = parse_qs(urlsplit(third_response.data["deep_link_url"]).query)[
            "start"
        ][0]
        TelegramLinkSession.objects.filter(id=third_response.data["id"]).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        expired = self._webhook(third_token, telegram_id=77)
        self.assertIn("invalid or expired", expired.data["text"])
        self.assertFalse(TelegramConnection.objects.filter(user=second_user).exists())

    def test_preferences_are_personal_and_workspace_member_scoped(self):
        response = self.client.patch(
            f"/api/v1/telegram/preferences?workspace_id={self.workspace.id}",
            {"website_changed": False, "monitor_failed": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["website_changed"])

        outsider = User.objects.create_user(
            email="outsider@example.com", password="correct horse battery staple"
        )
        outsider_client = APIClient()
        outsider_client.force_authenticate(outsider)
        denied = outsider_client.get(
            f"/api/v1/telegram/preferences?workspace_id={self.workspace.id}"
        )
        self.assertEqual(denied.status_code, 403)
        invalid = self.client.patch(
            f"/api/v1/telegram/preferences?workspace_id={self.workspace.id}",
            {"website_changed": "yes"},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)

    @patch("worker.tasks.dispatch_telegram_test.delay")
    def test_test_delivery_requires_connection_and_disconnect_removes_personal_state(
        self, test_delay
    ):
        missing = self.client.post(
            "/api/v1/telegram/test",
            {"workspace_id": str(self.workspace.id)},
            format="json",
        )
        self.assertEqual(missing.status_code, 409)
        _, token = self._create_link()
        self._webhook(token)
        queued = self.client.post(
            "/api/v1/telegram/test",
            {"workspace_id": str(self.workspace.id)},
            format="json",
        )
        self.assertEqual(queued.status_code, 202)
        test_delay.assert_called_once_with(str(self.user.id), str(self.workspace.id))

        disconnected = self.client.delete("/api/v1/telegram/connection")
        self.assertEqual(disconnected.status_code, 204)
        self.assertFalse(TelegramConnection.objects.filter(user=self.user).exists())
        self.assertFalse(
            TelegramNotificationPreference.objects.filter(user=self.user).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                actor_id=self.user.id, action="telegram.disconnected"
            ).exists()
        )

    @override_settings(
        TELEGRAM_ENABLED=False,
        TELEGRAM_BOT_TOKEN="",
        TELEGRAM_BOT_USERNAME="",
        TELEGRAM_WEBHOOK_SECRET="",
    )
    def test_unconfigured_deployment_reports_unavailable(self):
        status_response = self.client.get("/api/v1/telegram/connection")
        self.assertEqual(status_response.status_code, 200)
        self.assertFalse(status_response.data["available"])
        link_response = self.client.post(
            "/api/v1/telegram/link-sessions",
            {"workspace_id": str(self.workspace.id)},
            format="json",
        )
        self.assertEqual(link_response.status_code, 503)


@override_settings(**TELEGRAM_SETTINGS)
class TelegramDeliveryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="delivery@example.com", password="correct horse battery staple"
        )
        self.workspace = Workspace.objects.create(
            name="Delivery", type=Workspace.WorkspaceType.PERSONAL, owner=self.user
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.user,
            role=WorkspaceMember.Role.OWNER,
        )
        self.connection = TelegramConnection.objects.create(
            user=self.user,
            telegram_user_id=123,
            private_chat_id=123,
            username="delivery_user",
        )
        self.preference = TelegramNotificationPreference.objects.create(
            user=self.user, workspace=self.workspace
        )

    @patch("core.telegram.send_telegram_message", return_value="88")
    def test_delivery_is_idempotent_and_excludes_sensitive_payload(self, send):
        notification = Notification.objects.create(
            workspace=self.workspace,
            user=self.user,
            type=Notification.Type.TASK_COMPLETED,
            payload={
                "task_id": str(self.user.id),
                "title": "Prepare customer report",
                "status": "completed",
                "result": "SECRET CUSTOMER CONTENT",
                "error": "PRIVATE STACK TRACE",
            },
        )
        dispatch_notification_telegram(str(notification.id))
        dispatch_notification_telegram(str(notification.id))
        delivery = TelegramDelivery.objects.get(notification=notification)
        self.assertEqual(delivery.status, TelegramDelivery.Status.SENT)
        self.assertEqual(delivery.external_message_id, "88")
        send.assert_called_once()
        message = send.call_args.args[1]
        self.assertIn("Task completed", message)
        self.assertIn("Prepare customer report", message)
        self.assertNotIn("SECRET CUSTOMER CONTENT", message)
        self.assertNotIn("PRIVATE STACK TRACE", message)

    @patch("core.telegram.send_telegram_message")
    def test_disabled_event_is_skipped_without_sending(self, send):
        self.preference.website_changed = False
        self.preference.save(update_fields=["website_changed", "updated_at"])
        notification = Notification.objects.create(
            workspace=self.workspace,
            user=self.user,
            type=Notification.Type.WEBSITE_CHANGED,
            payload={
                "monitor_id": str(self.user.id),
                "title": "Competitor pricing",
                "change_summary": "Secret full-page diff",
            },
        )
        dispatch_notification_telegram(str(notification.id))
        self.assertEqual(
            TelegramDelivery.objects.get(notification=notification).status,
            TelegramDelivery.Status.SKIPPED,
        )
        send.assert_not_called()

    @patch("core.telegram.send_telegram_message")
    def test_revoked_workspace_member_is_skipped_before_delivery(self, send):
        notification = Notification.objects.create(
            workspace=self.workspace,
            user=self.user,
            type=Notification.Type.TASK_COMPLETED,
            payload={
                "task_id": str(self.user.id),
                "title": "Former workspace task",
                "status": "completed",
            },
        )
        WorkspaceMember.objects.filter(
            workspace=self.workspace, user=self.user
        ).delete()
        dispatch_notification_telegram(str(notification.id))
        self.assertEqual(
            TelegramDelivery.objects.get(notification=notification).status,
            TelegramDelivery.Status.SKIPPED,
        )
        send.assert_not_called()

    @patch(
        "core.telegram.send_telegram_message",
        side_effect=TelegramPermanentError("rejected"),
    )
    def test_permanent_destination_error_disables_connection(self, _send):
        notification = Notification.objects.create(
            workspace=self.workspace,
            user=self.user,
            type=Notification.Type.RESEARCH_COMPLETED,
            payload={"research_run_id": str(self.user.id), "title": "Market report"},
        )
        dispatch_notification_telegram(str(notification.id))
        self.connection.refresh_from_db()
        self.assertFalse(self.connection.enabled)
        self.assertEqual(
            TelegramDelivery.objects.get(notification=notification).last_error,
            "destination_rejected",
        )

    @patch("core.telegram.send_telegram_message", return_value="99")
    def test_processing_lease_is_retried_then_stale_delivery_recovers(self, send):
        notification = Notification.objects.create(
            workspace=self.workspace,
            user=self.user,
            type=Notification.Type.TASK_COMPLETED,
            payload={
                "task_id": str(self.user.id),
                "title": "Recover task",
                "status": "completed",
            },
        )
        delivery = TelegramDelivery.objects.create(
            notification=notification,
            connection=self.connection,
            status=TelegramDelivery.Status.PROCESSING,
            attempts=1,
        )
        with self.assertRaises(Retry):
            dispatch_notification_telegram(str(notification.id))
        send.assert_not_called()

        TelegramDelivery.objects.filter(id=delivery.id).update(
            updated_at=timezone.now() - timedelta(minutes=6)
        )
        dispatch_notification_telegram(str(notification.id))
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, TelegramDelivery.Status.SENT)
        send.assert_called_once()

    @patch("worker.tasks.dispatch_notification_telegram.delay")
    @patch("worker.tasks.dispatch_notification_email.delay")
    def test_enqueue_schedules_email_and_telegram_independently(
        self, email_delay, telegram_delay
    ):
        enqueue_notification_deliveries("notification-id")
        email_delay.assert_called_once_with("notification-id")
        telegram_delay.assert_called_once_with("notification-id")

    @patch(
        "worker.tasks.dispatch_notification_telegram.delay",
        side_effect=RuntimeError("broker unavailable"),
    )
    @patch("worker.tasks.dispatch_notification_email.delay")
    def test_telegram_enqueue_failure_is_recorded(self, _email_delay, _telegram_delay):
        notification = Notification.objects.create(
            workspace=self.workspace,
            user=self.user,
            type=Notification.Type.TASK_COMPLETED,
            payload={"title": "Queued task", "status": "completed"},
        )
        enqueue_notification_deliveries(str(notification.id))
        delivery = TelegramDelivery.objects.get(notification=notification)
        self.assertEqual(delivery.status, TelegramDelivery.Status.FAILED)
        self.assertEqual(delivery.last_error, "enqueue_failed")
