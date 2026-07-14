import pyotp
from django.conf import settings
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

import core.coworkers as coworker_service
from core.encryption import decrypt_from_text, encrypt_to_bytes, encrypt_to_text
from core.google_oauth import GoogleOAuthError, exchange_code_for_tokens, fetch_userinfo
from core.interface import write_audit_log
from core.models import (
    Coworker,
    CoworkerToolAttachment,
    OAuthIdentity,
    ProviderCredential,
    Team,
    Tool,
    User,
    Workspace,
    WorkspaceMember,
)
from core.permissions import IsWorkspaceMember, get_coworker_for_member, get_workspace_for_member
from core.provisioning import provision_personal_workspace
from core.serializers import (
    CoworkerCreateSerializer,
    CoworkerSerializer,
    CoworkerToolAttachmentSerializer,
    CoworkerUpdateSerializer,
    CoworkerVersionSerializer,
    GoogleOAuthCallbackSerializer,
    LoginSerializer,
    MFAEnrollConfirmSerializer,
    MFALoginVerifySerializer,
    ProviderCredentialSerializer,
    RegisterSerializer,
    ToolSerializer,
    UserSerializer,
    WorkspaceSerializer,
)

MFA_LOGIN_SALT = "mfa-login"
MFA_LOGIN_TOKEN_MAX_AGE = 300  # 5 minutes


class HealthView(APIView):
    # Must stay open — orchestrators/load balancers (and Dokploy's health
    # checks, ARCHITECTURE.md §8.1) hit this unauthenticated. Milestone 1's
    # switch to default-deny (IsAuthenticated) would otherwise break it.
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})


def _issue_tokens(user: User) -> dict:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def _error(code: str, message: str, http_status: int, details: dict | None = None) -> Response:
    return Response(
        {"error": {"code": code, "message": message, "details": details or {}}},
        status=http_status,
    )


def _personal_workspace_id(user: User) -> str | None:
    """Account-level events (login, MFA) aren't scoped to a workspace by the
    request. Most users have a PERSONAL workspace from registration
    (provision_personal_workspace) — use it as the natural home for these
    when it exists; AuditLog.workspace is nullable for the users who don't
    (e.g. guest-only members, or fixtures that skip provisioning)."""
    workspace = Workspace.objects.filter(
        owner=user, type=Workspace.WorkspaceType.PERSONAL
    ).first()
    return workspace.id if workspace else None


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = User.objects.create_user(
            email=data["email"], password=data["password"], display_name=data["display_name"]
        )
        workspace = provision_personal_workspace(user)
        write_audit_log(
            actor_type="user", actor_id=user.id, action="user.register",
            resource_type="user", resource_id=user.id, workspace_id=workspace.id,
        )
        return Response(
            {
                "user": UserSerializer(user).data,
                "workspace": WorkspaceSerializer(workspace).data,
                "tokens": _issue_tokens(user),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = User.objects.normalize_email(serializer.validated_data["email"])
        password = serializer.validated_data["password"]

        user = User.objects.filter(email__iexact=email).first()
        if user is None or not user.check_password(password) or not user.is_active:
            return _error("invalid_credentials", "Incorrect email or password.", 401)

        if user.mfa_enabled:
            mfa_token = signing.dumps({"user_id": str(user.id)}, salt=MFA_LOGIN_SALT)
            return Response({"mfa_required": True, "mfa_token": mfa_token})

        write_audit_log(
            actor_type="user", actor_id=user.id, action="user.login",
            resource_type="user", resource_id=user.id, workspace_id=_personal_workspace_id(user),
        )
        return Response({"tokens": _issue_tokens(user)})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        refresh = request.data.get("refresh")
        if not refresh:
            return _error("missing_refresh", "The 'refresh' field is required.", 400)
        try:
            RefreshToken(refresh).blacklist()
        except TokenError as exc:
            return _error("invalid_token", "Refresh token is invalid or already revoked.", 400,
                          {"detail": str(exc)})
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MFAEnrollView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        secret = pyotp.random_base32()
        request.user.mfa_secret = encrypt_to_text(secret)
        request.user.save(update_fields=["mfa_secret"])
        otpauth_url = pyotp.TOTP(secret).provisioning_uri(
            name=request.user.email, issuer_name=settings.MFA_ISSUER_NAME
        )
        return Response({"secret": secret, "otpauth_url": otpauth_url})


class MFAEnrollConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = MFAEnrollConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        if not user.mfa_secret:
            return _error("mfa_not_enrolled", "Call /auth/mfa/enroll first.", 400)

        secret = decrypt_from_text(user.mfa_secret)
        if not pyotp.TOTP(secret).verify(serializer.validated_data["code"], valid_window=1):
            return _error("invalid_code", "The provided code is incorrect or expired.", 400)

        user.mfa_enabled = True
        user.save(update_fields=["mfa_enabled"])
        write_audit_log(
            actor_type="user", actor_id=user.id, action="user.mfa_enabled",
            resource_type="user", resource_id=user.id, workspace_id=_personal_workspace_id(user),
        )
        return Response({"mfa_enabled": True})


class MFAVerifyView(APIView):
    """Completes a login that returned `mfa_required` — not authenticated,
    since the caller doesn't have tokens yet."""

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = MFALoginVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            payload = signing.loads(
                serializer.validated_data["mfa_token"],
                salt=MFA_LOGIN_SALT,
                max_age=MFA_LOGIN_TOKEN_MAX_AGE,
            )
        except (BadSignature, SignatureExpired):
            return _error(
                "invalid_mfa_token", "MFA session expired or invalid — log in again.", 400
            )

        user = User.objects.filter(id=payload["user_id"], mfa_enabled=True).first()
        if user is None or not user.mfa_secret:
            return _error("mfa_not_enrolled", "MFA is not enabled for this account.", 400)

        secret = decrypt_from_text(user.mfa_secret)
        if not pyotp.TOTP(secret).verify(serializer.validated_data["code"], valid_window=1):
            return _error("invalid_code", "The provided code is incorrect or expired.", 401)

        write_audit_log(
            actor_type="user", actor_id=user.id, action="user.login_mfa",
            resource_type="user", resource_id=user.id, workspace_id=_personal_workspace_id(user),
        )
        return Response({"tokens": _issue_tokens(user)})


class GoogleOAuthCallbackView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = GoogleOAuthCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            tokens = exchange_code_for_tokens(
                serializer.validated_data["code"], serializer.validated_data["redirect_uri"]
            )
            userinfo = fetch_userinfo(tokens["access_token"])
        except (GoogleOAuthError, KeyError) as exc:
            return _error("oauth_failed", "Google sign-in failed.", 400, {"detail": str(exc)})

        google_sub = userinfo.get("sub")
        email = userinfo.get("email")
        if not google_sub or not email:
            return _error("oauth_failed", "Google did not return the expected profile fields.", 400)

        identity = OAuthIdentity.objects.filter(
            provider=OAuthIdentity.Provider.GOOGLE, provider_user_id=google_sub
        ).first()

        if identity:
            user = identity.user
        else:
            user = User.objects.filter(email__iexact=User.objects.normalize_email(email)).first()
            is_new = user is None
            if is_new:
                user = User.objects.create_user(
                    email=email, password=None, display_name=userinfo.get("name", "")
                )
            OAuthIdentity.objects.create(
                user=user, provider=OAuthIdentity.Provider.GOOGLE, provider_user_id=google_sub
            )

        workspace = Workspace.objects.filter(
            owner=user, type=Workspace.WorkspaceType.PERSONAL
        ).first()
        if workspace is None:
            workspace = provision_personal_workspace(user)

        write_audit_log(
            actor_type="user", actor_id=user.id, action="user.login_google",
            resource_type="user", resource_id=user.id, workspace_id=workspace.id,
        )
        return Response(
            {
                "user": UserSerializer(user).data,
                "workspace": WorkspaceSerializer(workspace).data,
                "tokens": _issue_tokens(user),
            }
        )


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self) -> User:
        return self.request.user


class WorkspaceListView(generics.ListAPIView):
    """Workspaces the current user is a member of. Added alongside the rest of
    Milestone 1 (not in the original task list) because /auth/login and
    /auth/mfa/verify only return tokens, not a workspace — a client that
    isn't fresh off /auth/register or the Google callback needs some way to
    discover which workspace(s) it can act in. Matches the endpoint already
    documented in API.md §2."""

    serializer_class = WorkspaceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Workspace.objects.filter(members__user=self.request.user)


class WorkspaceDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = WorkspaceSerializer
    permission_classes = [IsAuthenticated, IsWorkspaceMember]
    queryset = Workspace.objects.all()
    lookup_url_kwarg = "workspace_id"


class ProviderCredentialListCreateView(generics.ListCreateAPIView):
    serializer_class = ProviderCredentialSerializer
    permission_classes = [IsAuthenticated]

    def _workspace(self) -> Workspace:
        return get_workspace_for_member(self.request.user, self.kwargs["workspace_id"])

    def get_queryset(self):
        return ProviderCredential.objects.filter(workspace=self._workspace())

    def perform_create(self, serializer: ProviderCredentialSerializer) -> None:
        api_key = serializer.validated_data.pop("api_key", None)
        serializer.save(
            workspace=self._workspace(),
            encrypted_key=encrypt_to_bytes(api_key) if api_key else None,
        )


class ProviderCredentialDestroyView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]

    def get_object(self) -> ProviderCredential:
        workspace = get_workspace_for_member(self.request.user, self.kwargs["workspace_id"])
        return get_object_or_404(
            ProviderCredential, workspace=workspace, id=self.kwargs["cred_id"]
        )


class ToolCatalogListView(generics.ListAPIView):
    """GET /api/v1/tools — the platform-wide catalog (DATABASE.md §2.3),
    not documented in API.md's original Coworkers section but needed for
    any attach-a-tool UI to show what's attachable. Added alongside the
    rest of Milestone 3, same pattern as Milestone 1's /workspaces list."""

    serializer_class = ToolSerializer
    permission_classes = [IsAuthenticated]
    queryset = Tool.objects.all().order_by("name")


class CoworkerListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, workspace_id: str) -> Response:
        workspace = get_workspace_for_member(request.user, workspace_id)
        coworkers = (
            Coworker.objects.filter(workspace=workspace, status=Coworker.Status.ACTIVE)
            .select_related("current_version__permission_profile")
            .prefetch_related("tool_attachments__tool")
            .order_by("-created_at")
        )
        return Response(CoworkerSerializer(coworkers, many=True).data)

    def post(self, request: Request, workspace_id: str) -> Response:
        workspace = get_workspace_for_member(request.user, workspace_id)
        serializer = CoworkerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        owner_type = data.get("owner_type", Coworker.OwnerType.USER)
        owner_id = data.get("owner_id")
        if owner_type == Coworker.OwnerType.USER:
            if owner_id is not None and owner_id != request.user.id:
                raise ValidationError({"owner_id": "A personal coworker must be owned by you."})
            owner_id = request.user.id
        else:
            membership = WorkspaceMember.objects.get(workspace=workspace, user=request.user)
            if membership.role not in (WorkspaceMember.Role.OWNER, WorkspaceMember.Role.ADMIN):
                raise PermissionDenied("Only workspace Owner/Admin can create shared coworkers.")
            if owner_type == Coworker.OwnerType.ORGANIZATION:
                if workspace.type != Workspace.WorkspaceType.ORGANIZATION:
                    raise ValidationError({"owner_type": "This workspace is not an organization."})
                owner_id = workspace.id
            elif not Team.objects.filter(id=owner_id, workspace=workspace).exists():
                raise ValidationError({"owner_id": "Team not found in this workspace."})

        coworker = coworker_service.create_coworker(
            workspace=workspace,
            owner_type=owner_type,
            owner_id=owner_id,
            created_by=request.user,
            name=data["name"],
            role_description=data["role_description"],
            model_binding=data["model_binding"],
            avatar_url=data.get("avatar_url"),
        )
        write_audit_log(
            actor_type="user", actor_id=request.user.id, action="coworker.create",
            resource_type="coworker", resource_id=coworker.id, workspace_id=workspace.id,
        )
        return Response(CoworkerSerializer(coworker).data, status=status.HTTP_201_CREATED)


class CoworkerDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, coworker_id: str) -> Response:
        coworker = get_coworker_for_member(request.user, coworker_id)
        return Response(CoworkerSerializer(coworker).data)

    def patch(self, request: Request, coworker_id: str) -> Response:
        coworker = get_coworker_for_member(request.user, coworker_id, require_write=True)
        serializer = CoworkerUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        name = data.get("name")
        avatar_url = data.get("avatar_url")
        if name is not None or avatar_url is not None:
            if name is not None:
                coworker.name = name
            if avatar_url is not None:
                coworker.avatar_url = avatar_url
            coworker.save(update_fields=["name", "avatar_url", "updated_at"])

        if "role_description" in data or "model_binding" in data:
            coworker_service.create_new_version(
                coworker,
                created_by=request.user,
                role_description=data.get("role_description"),
                model_binding=data.get("model_binding"),
                changelog=data.get("changelog"),
            )
            coworker.refresh_from_db()

        write_audit_log(
            actor_type="user", actor_id=request.user.id, action="coworker.update",
            resource_type="coworker", resource_id=coworker.id, workspace_id=coworker.workspace_id,
        )
        return Response(CoworkerSerializer(coworker).data)

    def delete(self, request: Request, coworker_id: str) -> Response:
        coworker = get_coworker_for_member(request.user, coworker_id, require_write=True)
        coworker.status = Coworker.Status.ARCHIVED
        coworker.save(update_fields=["status", "updated_at"])
        write_audit_log(
            actor_type="user", actor_id=request.user.id, action="coworker.archive",
            resource_type="coworker", resource_id=coworker.id, workspace_id=coworker.workspace_id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class CoworkerVersionsView(generics.ListAPIView):
    serializer_class = CoworkerVersionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        coworker = get_coworker_for_member(self.request.user, self.kwargs["coworker_id"])
        return coworker.versions.select_related("permission_profile", "created_by")


class CoworkerVersionRollbackView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, coworker_id: str, version_number: int) -> Response:
        coworker = get_coworker_for_member(request.user, coworker_id, require_write=True)
        target = get_object_or_404(
            coworker.versions, version_number=version_number
        )
        new_version = coworker_service.rollback_to_version(
            coworker, target, created_by=request.user
        )
        write_audit_log(
            actor_type="user", actor_id=request.user.id, action="coworker.rollback",
            resource_type="coworker", resource_id=coworker.id, workspace_id=coworker.workspace_id,
            metadata={"rolled_back_to": version_number, "new_version": new_version.version_number},
        )
        coworker.refresh_from_db()
        return Response(CoworkerSerializer(coworker).data)


class CoworkerToolAttachView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, coworker_id: str) -> Response:
        coworker = get_coworker_for_member(request.user, coworker_id, require_write=True)
        serializer = CoworkerToolAttachmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        attachment, created = CoworkerToolAttachment.objects.update_or_create(
            coworker=coworker,
            tool=serializer.validated_data["tool"],
            defaults={
                "config": serializer.validated_data.get("config", {}),
                "enabled": serializer.validated_data.get("enabled", True),
            },
        )
        write_audit_log(
            actor_type="user", actor_id=request.user.id, action="coworker.tool_attach",
            resource_type="coworker", resource_id=coworker.id, workspace_id=coworker.workspace_id,
            metadata={"tool_id": str(attachment.tool_id)},
        )
        return Response(
            CoworkerToolAttachmentSerializer(attachment).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class CoworkerToolDetachView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, coworker_id: str, tool_id: str) -> Response:
        coworker = get_coworker_for_member(request.user, coworker_id, require_write=True)
        attachment = get_object_or_404(
            CoworkerToolAttachment, coworker=coworker, tool_id=tool_id
        )
        attachment.delete()
        write_audit_log(
            actor_type="user", actor_id=request.user.id, action="coworker.tool_detach",
            resource_type="coworker", resource_id=coworker.id, workspace_id=coworker.workspace_id,
            metadata={"tool_id": str(tool_id)},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
