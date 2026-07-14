from __future__ import annotations

import hashlib

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from core.models import ApiToken


class ApiTokenAuthentication(BaseAuthentication):
    """Developer SDK bearer tokens, independently revocable from JWT sessions."""

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer agt_"):
            return None
        plaintext = header.removeprefix("Bearer ").strip()
        digest = hashlib.sha256(plaintext.encode()).hexdigest()
        token = ApiToken.objects.select_related("user").filter(
            token_hash=digest, revoked_at__isnull=True
        ).first()
        if token is None:
            raise AuthenticationFailed("Invalid or revoked API token.")
        token.last_used_at = timezone.now()
        token.save(update_fields=["last_used_at"])
        return token.user, token

    def authenticate_header(self, request):
        return "Bearer"
