from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from core.views import (
    GoogleOAuthCallbackView,
    LoginView,
    LogoutView,
    MeView,
    MFAEnrollConfirmView,
    MFAEnrollView,
    MFAVerifyView,
    ProviderCredentialDestroyView,
    ProviderCredentialListCreateView,
    RegisterView,
    WorkspaceDetailView,
    WorkspaceListView,
)

urlpatterns = [
    path("auth/register", RegisterView.as_view(), name="auth-register"),
    path("auth/login", LoginView.as_view(), name="auth-login"),
    path("auth/logout", LogoutView.as_view(), name="auth-logout"),
    path("auth/refresh", TokenRefreshView.as_view(), name="auth-refresh"),
    path(
        "auth/oauth/google/callback",
        GoogleOAuthCallbackView.as_view(),
        name="auth-oauth-google-callback",
    ),
    path("auth/mfa/enroll", MFAEnrollView.as_view(), name="auth-mfa-enroll"),
    path(
        "auth/mfa/enroll/confirm",
        MFAEnrollConfirmView.as_view(),
        name="auth-mfa-enroll-confirm",
    ),
    path("auth/mfa/verify", MFAVerifyView.as_view(), name="auth-mfa-verify"),
    path("me", MeView.as_view(), name="me"),
    path("workspaces", WorkspaceListView.as_view(), name="workspace-list"),
    path(
        "workspaces/<uuid:workspace_id>", WorkspaceDetailView.as_view(), name="workspace-detail"
    ),
    path(
        "workspaces/<uuid:workspace_id>/provider-credentials",
        ProviderCredentialListCreateView.as_view(),
        name="provider-credential-list-create",
    ),
    path(
        "workspaces/<uuid:workspace_id>/provider-credentials/<uuid:cred_id>",
        ProviderCredentialDestroyView.as_view(),
        name="provider-credential-destroy",
    ),
]
