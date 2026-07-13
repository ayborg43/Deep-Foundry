from unittest.mock import patch

import pyotp
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import OAuthIdentity, ProviderCredential, User, Workspace, WorkspaceMember

VALID_PASSWORD = "correct horse battery staple 42"


class HealthCheckStaysPublicTests(APITestCase):
    """Regression test: Milestone 1 flipped DEFAULT_PERMISSION_CLASSES to
    IsAuthenticated (default-deny). /health must stay reachable without auth
    for orchestrators/Dokploy — this broke once already during manual
    verification before HealthView got an explicit AllowAny override."""

    def test_health_does_not_require_authentication(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"status": "ok"})


class RegisterTests(APITestCase):
    def test_register_creates_user_workspace_and_tokens(self):
        response = self.client.post(
            reverse("auth-register"),
            {"email": "new@example.com", "password": VALID_PASSWORD, "display_name": "New User"},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIn("access", response.data["tokens"])
        self.assertIn("refresh", response.data["tokens"])
        self.assertEqual(response.data["user"]["email"], "new@example.com")

        user = User.objects.get(email="new@example.com")
        self.assertTrue(user.check_password(VALID_PASSWORD))
        workspace = Workspace.objects.get(owner=user)
        self.assertEqual(workspace.type, Workspace.WorkspaceType.PERSONAL)
        membership = WorkspaceMember.objects.get(workspace=workspace, user=user)
        self.assertEqual(membership.role, WorkspaceMember.Role.OWNER)

    def test_register_duplicate_email_fails(self):
        User.objects.create_user(email="dup@example.com", password=VALID_PASSWORD)
        response = self.client.post(
            reverse("auth-register"), {"email": "dup@example.com", "password": VALID_PASSWORD}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_weak_password_fails(self):
        response = self.client.post(
            reverse("auth-register"), {"email": "weak@example.com", "password": "123"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LoginTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="login@example.com", password=VALID_PASSWORD)

    def test_login_success_returns_tokens(self):
        response = self.client.post(
            reverse("auth-login"), {"email": "login@example.com", "password": VALID_PASSWORD}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data["tokens"])

    def test_login_wrong_password_fails(self):
        response = self.client.post(
            reverse("auth-login"), {"email": "login@example.com", "password": "wrong"}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"]["code"], "invalid_credentials")

    def test_login_with_mfa_enabled_returns_mfa_required_not_tokens(self):
        self.user.mfa_enabled = True
        self.user.mfa_secret = "irrelevant-for-this-test"
        self.user.save()
        response = self.client.post(
            reverse("auth-login"), {"email": "login@example.com", "password": VALID_PASSWORD}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["mfa_required"])
        self.assertIn("mfa_token", response.data)
        self.assertNotIn("tokens", response.data)


class RefreshLogoutTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="rl@example.com", password=VALID_PASSWORD)
        login = self.client.post(
            reverse("auth-login"), {"email": "rl@example.com", "password": VALID_PASSWORD}
        )
        self.tokens = login.data["tokens"]

    def test_refresh_rotates_and_returns_new_tokens(self):
        response = self.client.post(reverse("auth-refresh"), {"refresh": self.tokens["refresh"]})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertNotEqual(response.data["access"], self.tokens["access"])

    def test_logout_blacklists_refresh_token(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.tokens['access']}")
        response = self.client.post(reverse("auth-logout"), {"refresh": self.tokens["refresh"]})
        self.assertEqual(response.status_code, status.HTTP_205_RESET_CONTENT)

        # The blacklisted refresh token must no longer work.
        self.client.credentials()
        replay = self.client.post(reverse("auth-refresh"), {"refresh": self.tokens["refresh"]})
        self.assertEqual(replay.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_requires_authentication(self):
        self.client.credentials()
        response = self.client.post(reverse("auth-logout"), {"refresh": self.tokens["refresh"]})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class MeTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="me@example.com", password=VALID_PASSWORD, display_name="Original"
        )

    def _auth(self):
        login = self.client.post(
            reverse("auth-login"), {"email": "me@example.com", "password": VALID_PASSWORD}
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['tokens']['access']}")

    def test_me_requires_authentication(self):
        response = self.client.get(reverse("me"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_get_returns_current_user(self):
        self._auth()
        response = self.client.get(reverse("me"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "me@example.com")

    def test_me_patch_updates_display_name(self):
        self._auth()
        response = self.client.patch(reverse("me"), {"display_name": "Updated"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.display_name, "Updated")

    def test_me_patch_cannot_change_email(self):
        self._auth()
        self.client.patch(reverse("me"), {"email": "hijack@example.com"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "me@example.com")


class WorkspaceTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@example.com", password=VALID_PASSWORD)
        self.stranger = User.objects.create_user(
            email="stranger@example.com", password=VALID_PASSWORD
        )
        self.workspace = Workspace.objects.create(
            name="Owner's Workspace", type=Workspace.WorkspaceType.PERSONAL, owner=self.owner
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace, user=self.owner, role=WorkspaceMember.Role.OWNER
        )

    def _auth_as(self, user, password=VALID_PASSWORD):
        login = self.client.post(
            reverse("auth-login"), {"email": user.email, "password": password}
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['tokens']['access']}")

    def test_list_returns_only_workspaces_user_is_member_of(self):
        self._auth_as(self.owner)
        response = self.client.get(reverse("workspace-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [w["id"] for w in response.data]
        self.assertIn(str(self.workspace.id), ids)

        self._auth_as(self.stranger)
        response = self.client.get(reverse("workspace-list"))
        self.assertEqual(response.data, [])

    def test_owner_can_get_workspace(self):
        self._auth_as(self.owner)
        response = self.client.get(
            reverse("workspace-detail", kwargs={"workspace_id": self.workspace.id})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Owner's Workspace")

    def test_owner_can_patch_workspace_name(self):
        self._auth_as(self.owner)
        response = self.client.patch(
            reverse("workspace-detail", kwargs={"workspace_id": self.workspace.id}),
            {"name": "Renamed"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.name, "Renamed")

    def test_non_member_cannot_get_workspace(self):
        self._auth_as(self.stranger)
        response = self.client.get(
            reverse("workspace-detail", kwargs={"workspace_id": self.workspace.id})
        )
        # Consistent with ProviderCredential's get_workspace_for_member: 403
        # (exists, access denied), not 404 (hidden) — see core/permissions.py.
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class MFATests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="mfa@example.com", password=VALID_PASSWORD)
        login = self.client.post(
            reverse("auth-login"), {"email": "mfa@example.com", "password": VALID_PASSWORD}
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['tokens']['access']}")

    def test_enroll_returns_secret_and_otpauth_url(self):
        response = self.client.post(reverse("auth-mfa-enroll"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("secret", response.data)
        self.assertTrue(response.data["otpauth_url"].startswith("otpauth://totp/"))

    def test_confirm_with_wrong_code_fails_and_does_not_enable(self):
        self.client.post(reverse("auth-mfa-enroll"))
        response = self.client.post(reverse("auth-mfa-enroll-confirm"), {"code": "000000"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertFalse(self.user.mfa_enabled)

    def test_full_enroll_and_login_flow(self):
        enroll = self.client.post(reverse("auth-mfa-enroll"))
        secret = enroll.data["secret"]
        valid_code = pyotp.TOTP(secret).now()

        confirm = self.client.post(reverse("auth-mfa-enroll-confirm"), {"code": valid_code})
        self.assertEqual(confirm.status_code, status.HTTP_200_OK)
        self.assertTrue(confirm.data["mfa_enabled"])

        # Now a normal login must demand MFA instead of returning tokens directly.
        self.client.credentials()
        login = self.client.post(
            reverse("auth-login"), {"email": "mfa@example.com", "password": VALID_PASSWORD}
        )
        self.assertTrue(login.data["mfa_required"])

        verify = self.client.post(
            reverse("auth-mfa-verify"),
            {"mfa_token": login.data["mfa_token"], "code": pyotp.TOTP(secret).now()},
        )
        self.assertEqual(verify.status_code, status.HTTP_200_OK)
        self.assertIn("access", verify.data["tokens"])

    def test_verify_with_wrong_code_rejected(self):
        enroll = self.client.post(reverse("auth-mfa-enroll"))
        secret = enroll.data["secret"]
        self.client.post(
            reverse("auth-mfa-enroll-confirm"), {"code": pyotp.TOTP(secret).now()}
        )
        self.client.credentials()
        login = self.client.post(
            reverse("auth-login"), {"email": "mfa@example.com", "password": VALID_PASSWORD}
        )
        verify = self.client.post(
            reverse("auth-mfa-verify"), {"mfa_token": login.data["mfa_token"], "code": "000000"}
        )
        self.assertEqual(verify.status_code, status.HTTP_401_UNAUTHORIZED)


class ProviderCredentialTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="pc@example.com", password=VALID_PASSWORD)
        self.stranger = User.objects.create_user(
            email="pcstranger@example.com", password=VALID_PASSWORD
        )
        self.workspace = Workspace.objects.create(
            name="PC Workspace", type=Workspace.WorkspaceType.PERSONAL, owner=self.owner
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace, user=self.owner, role=WorkspaceMember.Role.OWNER
        )
        login = self.client.post(
            reverse("auth-login"), {"email": "pc@example.com", "password": VALID_PASSWORD}
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['tokens']['access']}")

    def _url(self):
        return reverse(
            "provider-credential-list-create", kwargs={"workspace_id": self.workspace.id}
        )

    def test_create_never_returns_plaintext_key(self):
        response = self.client.post(
            self._url(),
            {
                "label": "My DeepSeek key",
                "deployment_mode": "deepseek_cloud",
                "api_key": "sk-super-secret-value-123",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertNotIn("api_key", response.data)
        self.assertNotIn("sk-super-secret-value-123", str(response.data))
        self.assertTrue(response.data["masked_key"].startswith("sk-s"))
        self.assertTrue(response.data["masked_key"].endswith("-123"))

        stored = ProviderCredential.objects.get(id=response.data["id"])
        self.assertNotEqual(bytes(stored.encrypted_key), b"sk-super-secret-value-123")

    def test_self_hosted_mode_rejected_at_mvp(self):
        response = self.client.post(
            self._url(),
            {"label": "x", "deployment_mode": "deepseek_self_hosted", "api_key": "irrelevant"},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_never_returns_plaintext(self):
        self.client.post(
            self._url(),
            {"label": "k1", "deployment_mode": "deepseek_cloud", "api_key": "sk-abcdefgh"},
        )
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("sk-abcdefgh", str(response.data))

    def test_delete_removes_credential(self):
        create = self.client.post(
            self._url(),
            {"label": "to-delete", "deployment_mode": "deepseek_cloud", "api_key": "sk-zzzz"},
        )
        delete_url = reverse(
            "provider-credential-destroy",
            kwargs={"workspace_id": self.workspace.id, "cred_id": create.data["id"]},
        )
        response = self.client.delete(delete_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ProviderCredential.objects.filter(id=create.data["id"]).exists())

    def test_non_member_forbidden(self):
        self.client.credentials()
        login = self.client.post(
            reverse("auth-login"),
            {"email": "pcstranger@example.com", "password": VALID_PASSWORD},
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {login.data['tokens']['access']}"
        )
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class GoogleOAuthTests(APITestCase):
    """The Google-side handshake (real client credentials, real consent
    screen) can't be exercised in this environment — these tests mock the
    two network calls in core.google_oauth and verify our own linking logic."""

    @patch("core.views.fetch_userinfo")
    @patch("core.views.exchange_code_for_tokens")
    def test_new_user_created_on_first_google_login(self, mock_exchange, mock_userinfo):
        mock_exchange.return_value = {"access_token": "fake-google-access-token"}
        mock_userinfo.return_value = {
            "sub": "google-subject-123",
            "email": "googleuser@example.com",
            "name": "Google User",
        }

        response = self.client.post(
            reverse("auth-oauth-google-callback"),
            {"code": "fake-code", "redirect_uri": "http://localhost:3000/auth/google/callback"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["user"]["email"], "googleuser@example.com")
        self.assertIn("access", response.data["tokens"])

        user = User.objects.get(email="googleuser@example.com")
        self.assertFalse(user.has_usable_password())
        identity = OAuthIdentity.objects.get(user=user)
        self.assertEqual(identity.provider_user_id, "google-subject-123")
        self.assertTrue(Workspace.objects.filter(owner=user).exists())

    @patch("core.views.fetch_userinfo")
    @patch("core.views.exchange_code_for_tokens")
    def test_second_login_reuses_same_user_no_duplicate_workspace(
        self, mock_exchange, mock_userinfo
    ):
        mock_exchange.return_value = {"access_token": "fake-google-access-token"}
        mock_userinfo.return_value = {
            "sub": "google-subject-456",
            "email": "repeat@example.com",
            "name": "Repeat User",
        }
        url = reverse("auth-oauth-google-callback")
        body = {"code": "fake-code", "redirect_uri": "http://localhost:3000/auth/google/callback"}

        first = self.client.post(url, body)
        second = self.client.post(url, body)

        self.assertEqual(first.data["user"]["id"], second.data["user"]["id"])
        self.assertEqual(
            Workspace.objects.filter(owner_id=first.data["user"]["id"]).count(), 1
        )
        identity_count = OAuthIdentity.objects.filter(
            provider_user_id="google-subject-456"
        ).count()
        self.assertEqual(identity_count, 1)

    @patch("core.views.fetch_userinfo")
    @patch("core.views.exchange_code_for_tokens")
    def test_links_to_existing_email_password_account(self, mock_exchange, mock_userinfo):
        existing = User.objects.create_user(email="already@example.com", password=VALID_PASSWORD)
        mock_exchange.return_value = {"access_token": "fake-google-access-token"}
        mock_userinfo.return_value = {
            "sub": "google-subject-789",
            "email": "already@example.com",
            "name": "Already Registered",
        }
        response = self.client.post(
            reverse("auth-oauth-google-callback"),
            {"code": "fake-code", "redirect_uri": "http://localhost:3000/auth/google/callback"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["id"], str(existing.id))
