from __future__ import annotations

import hashlib

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from core.models import SCIMToken


class SCIMTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer scm_"):
            raise AuthenticationFailed("A SCIM bearer token is required.")
        digest = hashlib.sha256(header.removeprefix("Bearer ").strip().encode()).hexdigest()
        token = SCIMToken.objects.select_related("workspace__owner").filter(
            token_hash=digest, revoked_at__isnull=True
        ).first()
        if token is None:
            raise AuthenticationFailed("Invalid or revoked SCIM token.")
        token.last_used_at = timezone.now()
        token.save(update_fields=["last_used_at"])
        return token.workspace.owner, token

    def authenticate_header(self, request):
        return 'Bearer realm="SCIM"'
