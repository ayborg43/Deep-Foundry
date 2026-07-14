"""
End-to-end tests of the internal test-harness FastAPI endpoints — real Django
auth (JWTs from simplejwt), real workspace/credential fixtures, real ASGI
routing through ai.main.app. Only the DeepSeek network boundary is mocked
(no live API key in this environment).

Uses TransactionTestCase, not TestCase: Starlette's TestClient drives the
ASGI app on its own thread/event loop, and our FastAPI dependencies reach
Django via sync_to_async — a different DB connection than the test's own
thread. TestCase's per-test wrapping transaction is invisible to that other
connection (nothing's committed yet), so fixtures created in setUp() would
look like they don't exist. TransactionTestCase actually commits (and
truncates between tests instead), which is visible everywhere.
"""

from unittest.mock import patch

from django.test import TransactionTestCase
from fastapi.testclient import TestClient
from rest_framework_simplejwt.tokens import RefreshToken

from ai.main import app
from ai.model_router.adapters.deepseek_cloud import DeepSeekCloudAdapter
from ai.models import ModelCall
from core.encryption import encrypt_to_bytes
from core.models import ProviderCredential, User, Workspace, WorkspaceMember


class EndpointTestBase(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="endpoint@example.com", password="x")
        self.workspace = Workspace.objects.create(
            name="Endpoint WS", type=Workspace.WorkspaceType.PERSONAL, owner=self.user
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace, user=self.user, role=WorkspaceMember.Role.OWNER
        )
        self.access_token = str(RefreshToken.for_user(self.user).access_token)
        self.client = TestClient(app)

    def _headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    def _add_credential(self, api_key="sk-test-key"):
        ProviderCredential.objects.create(
            workspace=self.workspace,
            deployment_mode=ProviderCredential.DeploymentMode.DEEPSEEK_CLOUD,
            encrypted_key=encrypt_to_bytes(api_key),
            label="test",
            is_default=True,
        )


class AuthAndMembershipTests(EndpointTestBase):
    def _payload(self):
        return {"workspace_id": str(self.workspace.id), "model_id": "deepseek-v4-flash", "messages": []}

    def test_generate_requires_authentication(self):
        response = self.client.post("/internal/generate", json=self._payload())
        self.assertEqual(response.status_code, 401)

    def test_generate_rejects_non_member(self):
        stranger = User.objects.create_user(email="stranger@example.com", password="x")
        token = str(RefreshToken.for_user(stranger).access_token)
        response = self.client.post(
            "/internal/generate",
            json=self._payload(),
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 403)

    def test_generate_without_credential_returns_424(self):
        response = self.client.post(
            "/internal/generate", json=self._payload(), headers=self._headers()
        )
        self.assertEqual(response.status_code, 424)


class GenerateEndpointTests(EndpointTestBase):
    def setUp(self):
        super().setUp()
        self._add_credential()

    @patch.object(DeepSeekCloudAdapter, "_post")
    def test_generate_returns_normalized_response(self, mock_post):
        mock_post.return_value = {
            "id": "x",
            "model": "deepseek-v4-flash",
            "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2},
        }
        response = self.client.post(
            "/internal/generate",
            json={
                "workspace_id": str(self.workspace.id),
                "model_id": "deepseek-v4-flash",
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers=self._headers(),
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["content"], "Hello!")
        self.assertEqual(body["usage"]["input_tokens"], 4)
        self.assertEqual(ModelCall.objects.count(), 1)

    @patch.object(DeepSeekCloudAdapter, "_post")
    def test_generate_with_tools_against_tool_capable_model_succeeds(self, mock_post):
        mock_post.return_value = {
            "id": "x",
            "model": "deepseek-v4-pro",
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
        response = self.client.post(
            "/internal/generate",
            json={
                "workspace_id": str(self.workspace.id),
                "model_id": "deepseek-v4-pro",
                "messages": [{"role": "user", "content": "hi"}],
                "tools": [{"name": "t", "description": "d", "parameters": {}}],
            },
            headers=self._headers(),
        )
        self.assertEqual(response.status_code, 200, response.text)
        mock_post.assert_called_once()

    @patch.object(DeepSeekCloudAdapter, "_post")
    def test_generate_unknown_model_id_fails_before_network_call(self, mock_post):
        response = self.client.post(
            "/internal/generate",
            json={
                "workspace_id": str(self.workspace.id),
                "model_id": "not-a-real-model",
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers=self._headers(),
        )
        self.assertGreaterEqual(response.status_code, 400)
        mock_post.assert_not_called()

    @patch.object(DeepSeekCloudAdapter, "_post")
    def test_generate_adapter_error_returns_502(self, mock_post):
        from ai.model_router.errors import AdapterError

        mock_post.side_effect = AdapterError("upstream broke")
        response = self.client.post(
            "/internal/generate",
            json={
                "workspace_id": str(self.workspace.id),
                "model_id": "deepseek-v4-flash",
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers=self._headers(),
        )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(ModelCall.objects.get().status, ModelCall.Status.ERROR)


class StreamEndpointTests(EndpointTestBase):
    def setUp(self):
        super().setUp()
        self._add_credential()

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_stream_endpoint_returns_sse_chunks(self, mock_stream):
        mock_stream.return_value = iter(
            [
                {"choices": [{"delta": {"content": "Hi"}, "finish_reason": None}]},
                {
                    "choices": [{"delta": {}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                },
            ]
        )
        with self.client.stream(
            "POST",
            "/internal/generate/stream",
            json={
                "workspace_id": str(self.workspace.id),
                "model_id": "deepseek-v4-flash",
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers=self._headers(),
        ) as response:
            self.assertEqual(response.status_code, 200)
            body = "".join(response.iter_text())

        self.assertIn("event: chunk", body)
        self.assertIn('"delta": "Hi"', body)
        self.assertIn('"finish_reason": "stop"', body)
        self.assertEqual(ModelCall.objects.count(), 1)
        self.assertEqual(ModelCall.objects.get().status, ModelCall.Status.SUCCESS)
