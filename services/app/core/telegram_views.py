from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.interface import write_audit_log
from core.models import (
    AuditLog,
    TelegramConnection,
    TelegramLinkSession,
    TelegramNotificationPreference,
    User,
    WorkspaceMember,
)
from core.permissions import get_workspace_for_member
from core.telegram import normalized_bot_username, telegram_deep_link, telegram_is_configured

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{40,64}$")
_PREFERENCE_FIELDS = (
    "enabled",
    "task_completed",
    "research_completed",
    "website_changed",
    "approval_requested",
    "task_failed",
    "monitor_failed",
)


def _error(code: str, message: str, http_status: int) -> Response:
    return Response(
        {"error": {"code": code, "message": message, "details": {}}},
        status=http_status,
    )


def _connection_data(user) -> dict:
    available = telegram_is_configured()
    connection = TelegramConnection.objects.filter(user=user, enabled=True).first()
    data = {
        "available": available,
        "connected": connection is not None,
        "bot_username": normalized_bot_username() if available else "",
    }
    if connection:
        data.update(
            {
                "telegram_user_id": str(connection.telegram_user_id),
                "username": connection.username,
                "display_name": connection.display_name,
                "connected_at": connection.connected_at,
            }
        )
    return data


def _session_status(link_session: TelegramLinkSession) -> str:
    if link_session.used_at:
        return "linked"
    if link_session.cancelled_at:
        return "cancelled"
    if link_session.expires_at <= timezone.now():
        return "expired"
    return "pending"


def _preference_data(preference: TelegramNotificationPreference) -> dict:
    return {
        "workspace_id": str(preference.workspace_id),
        **{field: getattr(preference, field) for field in _PREFERENCE_FIELDS},
    }


class TelegramConnectionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(_connection_data(request.user))

    def delete(self, request: Request) -> Response:
        with transaction.atomic():
            connection = (
                TelegramConnection.objects.select_for_update()
                .filter(user=request.user)
                .first()
            )
            if connection is None:
                return Response(status=status.HTTP_204_NO_CONTENT)
            connection_id = connection.id
            connection.delete()
            TelegramLinkSession.objects.filter(user=request.user, used_at__isnull=True).delete()
            TelegramNotificationPreference.objects.filter(user=request.user).delete()
            write_audit_log(
                AuditLog.ActorType.USER,
                request.user.id,
                "telegram.disconnected",
                "telegram_connection",
                connection_id,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class TelegramLinkSessionCreateView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "telegram_link"

    def post(self, request: Request) -> Response:
        if not telegram_is_configured():
            return _error(
                "telegram_not_configured",
                "Telegram notifications are not configured on this deployment.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        workspace_id = request.data.get("workspace_id")
        if not workspace_id:
            return _error(
                "workspace_required",
                "Choose a workspace before connecting Telegram.",
                status.HTTP_400_BAD_REQUEST,
            )
        workspace = get_workspace_for_member(request.user, workspace_id)
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("ascii")).hexdigest()
        now = timezone.now()
        with transaction.atomic():
            # Lock a stable per-user row so concurrent requests cannot both
            # leave an active bearer token behind.
            User.objects.select_for_update().get(id=request.user.id)
            TelegramLinkSession.objects.filter(
                user=request.user,
                used_at__isnull=True,
                cancelled_at__isnull=True,
                expires_at__gt=now,
            ).update(cancelled_at=now)
            link_session = TelegramLinkSession.objects.create(
                user=request.user,
                workspace=workspace,
                token_hash=token_hash,
                expires_at=now + timedelta(seconds=settings.TELEGRAM_LINK_TTL_SECONDS),
            )
        return Response(
            {
                "id": str(link_session.id),
                "status": "pending",
                "deep_link_url": telegram_deep_link(raw_token),
                "expires_at": link_session.expires_at,
            },
            status=status.HTTP_201_CREATED,
        )


class TelegramLinkSessionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, session_id: str) -> Response:
        try:
            link_session = TelegramLinkSession.objects.get(
                id=session_id, user=request.user
            )
        except (TelegramLinkSession.DoesNotExist, ValueError):
            return _error(
                "not_found", "Telegram link session not found.", status.HTTP_404_NOT_FOUND
            )
        return Response(
            {
                "id": str(link_session.id),
                "status": _session_status(link_session),
                "expires_at": link_session.expires_at,
            }
        )


class TelegramPreferenceView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_preference(self, request: Request):
        workspace_id = request.query_params.get("workspace_id")
        if not workspace_id:
            return None, _error(
                "workspace_required",
                "The workspace_id query parameter is required.",
                status.HTTP_400_BAD_REQUEST,
            )
        workspace = get_workspace_for_member(request.user, workspace_id)
        preference, _ = TelegramNotificationPreference.objects.get_or_create(
            user=request.user, workspace=workspace
        )
        return preference, None

    def get(self, request: Request) -> Response:
        preference, error = self._get_preference(request)
        if error:
            return error
        return Response(_preference_data(preference))

    def patch(self, request: Request) -> Response:
        preference, error = self._get_preference(request)
        if error:
            return error
        unknown = set(request.data) - set(_PREFERENCE_FIELDS)
        if unknown:
            return _error(
                "invalid_preferences",
                "One or more notification preferences are not supported.",
                status.HTTP_400_BAD_REQUEST,
            )
        for field, value in request.data.items():
            if not isinstance(value, bool):
                return _error(
                    "invalid_preferences",
                    "Notification preferences must be true or false.",
                    status.HTTP_400_BAD_REQUEST,
                )
            setattr(preference, field, value)
        preference.save(update_fields=[*request.data.keys(), "updated_at"])
        write_audit_log(
            AuditLog.ActorType.USER,
            request.user.id,
            "telegram.preferences_updated",
            "telegram_notification_preference",
            preference.id,
            {"fields": sorted(request.data.keys())},
            workspace_id=preference.workspace_id,
        )
        return Response(_preference_data(preference))


class TelegramTestView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "telegram_test"

    def post(self, request: Request) -> Response:
        workspace_id = request.data.get("workspace_id")
        if not workspace_id:
            return _error(
                "workspace_required",
                "Choose a workspace before sending a test.",
                status.HTTP_400_BAD_REQUEST,
            )
        workspace = get_workspace_for_member(request.user, workspace_id)
        if not TelegramConnection.objects.filter(user=request.user, enabled=True).exists():
            return _error(
                "telegram_not_connected",
                "Connect Telegram before sending a test.",
                status.HTTP_409_CONFLICT,
            )
        from worker.tasks import dispatch_telegram_test

        dispatch_telegram_test.delay(str(request.user.id), str(workspace.id))
        return Response({"status": "queued"}, status=status.HTTP_202_ACCEPTED)


def _webhook_message(chat_id: int | None, text: str) -> Response:
    if chat_id is None:
        return Response({"ok": True})
    return Response(
        {
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
    )


class TelegramWebhookView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes: list = []

    def post(self, request: Request) -> Response:
        configured_secret = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "")
        supplied_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not configured_secret or not hmac.compare_digest(
            supplied_secret.encode("utf-8"), configured_secret.encode("utf-8")
        ):
            return _error(
                "invalid_webhook_secret",
                "Invalid Telegram webhook secret.",
                status.HTTP_403_FORBIDDEN,
            )
        content_length = request.META.get("CONTENT_LENGTH")
        try:
            if content_length and int(content_length) > settings.TELEGRAM_WEBHOOK_MAX_BYTES:
                return _error(
                    "update_too_large",
                    "Telegram update is too large.",
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                )
        except (TypeError, ValueError):
            return _error(
                "invalid_update", "Invalid Telegram update.", status.HTTP_400_BAD_REQUEST
            )
        try:
            raw_body = request.body
        except Exception:
            return _error(
                "invalid_update", "Invalid Telegram update.", status.HTTP_400_BAD_REQUEST
            )
        if len(raw_body) > settings.TELEGRAM_WEBHOOK_MAX_BYTES:
            return _error(
                "update_too_large",
                "Telegram update is too large.",
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        try:
            update = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _error(
                "invalid_update", "Invalid Telegram update.", status.HTTP_400_BAD_REQUEST
            )
        if not isinstance(update, dict):
            return _error(
                "invalid_update", "Invalid Telegram update.", status.HTTP_400_BAD_REQUEST
            )
        message = update.get("message")
        if not isinstance(message, dict):
            return Response({"ok": True})
        chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        sender = message.get("from") if isinstance(message.get("from"), dict) else {}
        chat_id = chat.get("id")
        telegram_user_id = sender.get("id")
        if (
            chat.get("type") != "private"
            or not isinstance(chat_id, int)
            or not isinstance(telegram_user_id, int)
            or chat_id != telegram_user_id
        ):
            return Response({"ok": True})
        text = message.get("text")
        if not isinstance(text, str):
            return Response({"ok": True})
        match = re.fullmatch(r"/start(?:@[A-Za-z0-9_]+)?\s+([A-Za-z0-9_-]+)", text.strip())
        if not match or not _TOKEN_RE.fullmatch(match.group(1)):
            return _webhook_message(
                chat_id, "Open Deep Foundry and choose Connect Telegram to create a new link."
            )
        token_hash = hashlib.sha256(match.group(1).encode("ascii")).hexdigest()
        now = timezone.now()
        with transaction.atomic():
            link_session = (
                TelegramLinkSession.objects.select_for_update()
                .select_related("user", "workspace")
                .filter(token_hash=token_hash)
                .first()
            )
            if (
                link_session is None
                or link_session.used_at is not None
                or link_session.cancelled_at is not None
                or link_session.expires_at <= now
            ):
                return _webhook_message(
                    chat_id,
                    "This Telegram connection link is invalid or expired. Create a new one in Deep Foundry.",
                )
            if not WorkspaceMember.objects.filter(
                workspace=link_session.workspace, user=link_session.user
            ).exists():
                link_session.cancelled_at = now
                link_session.save(update_fields=["cancelled_at"])
                return _webhook_message(
                    chat_id,
                    "This Telegram connection link is no longer valid. Create a new one in Deep Foundry.",
                )
            collision = (
                TelegramConnection.objects.select_for_update()
                .filter(
                    Q(telegram_user_id=telegram_user_id) | Q(private_chat_id=chat_id)
                )
                .exclude(user=link_session.user)
                .exists()
            )
            if collision:
                link_session.cancelled_at = now
                link_session.save(update_fields=["cancelled_at"])
                return _webhook_message(
                    chat_id,
                    "This Telegram account is already connected to another Deep Foundry user.",
                )
            display_name = " ".join(
                part
                for part in (str(sender.get("first_name") or ""), str(sender.get("last_name") or ""))
                if part
            )[:255]
            try:
                # The nested savepoint lets us recover neutrally if another
                # webhook wins a uniqueness race after the collision check.
                with transaction.atomic():
                    connection = (
                        TelegramConnection.objects.select_for_update()
                        .filter(user=link_session.user)
                        .first()
                    )
                    if connection is None:
                        connection = TelegramConnection.objects.create(
                            user=link_session.user,
                            telegram_user_id=telegram_user_id,
                            private_chat_id=chat_id,
                            username=str(sender.get("username") or "")[:64] or None,
                            display_name=display_name,
                        )
                    else:
                        connection.telegram_user_id = telegram_user_id
                        connection.private_chat_id = chat_id
                        connection.username = str(sender.get("username") or "")[:64] or None
                        connection.display_name = display_name
                        connection.enabled = True
                        connection.save(
                            update_fields=[
                                "telegram_user_id",
                                "private_chat_id",
                                "username",
                                "display_name",
                                "enabled",
                                "last_confirmed_at",
                            ]
                        )
            except IntegrityError:
                link_session.cancelled_at = now
                link_session.save(update_fields=["cancelled_at"])
                return _webhook_message(
                    chat_id,
                    "This Telegram account is already connected to another Deep Foundry user.",
                )
            TelegramNotificationPreference.objects.get_or_create(
                user=link_session.user, workspace=link_session.workspace
            )
            link_session.used_at = now
            link_session.save(update_fields=["used_at"])
            write_audit_log(
                AuditLog.ActorType.USER,
                link_session.user_id,
                "telegram.connected",
                "telegram_connection",
                connection.id,
                workspace_id=link_session.workspace_id,
            )
        return _webhook_message(
            chat_id,
            "Telegram notifications are connected. You can choose alerts in Deep Foundry settings.",
        )
