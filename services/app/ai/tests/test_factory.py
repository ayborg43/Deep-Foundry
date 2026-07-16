"""build_model_router credential resolution: workspace credential vs the
instance-wide DEEPSEEK_API_KEY fallback."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from ai.model_router.adapters.deepseek_cloud import DeepSeekCloudAdapter
from ai.model_router.factory import build_model_router
from core.interface import CredentialNotFoundError


class BuildModelRouterTests(TestCase):
    def test_falls_back_to_instance_wide_key(self):
        with patch(
            "ai.model_router.factory.get_provider_credential",
            side_effect=CredentialNotFoundError("none"),
        ), override_settings(DEEPSEEK_API_KEY="sk-central-123"):
            router = build_model_router(workspace_id="00000000-0000-0000-0000-000000000000")
        self.assertIsInstance(router.adapter, DeepSeekCloudAdapter)
        self.assertEqual(router.adapter.api_key, "sk-central-123")

    def test_no_credential_and_no_env_key_raises(self):
        with patch(
            "ai.model_router.factory.get_provider_credential",
            side_effect=CredentialNotFoundError("none"),
        ), override_settings(DEEPSEEK_API_KEY=""):
            with self.assertRaises(CredentialNotFoundError):
                build_model_router(workspace_id="00000000-0000-0000-0000-000000000000")

    def test_workspace_credential_overrides_env_key(self):
        class FakeCred:
            api_key = "sk-workspace-999"
            endpoint_url = None

        with patch(
            "ai.model_router.factory.get_provider_credential", return_value=FakeCred()
        ), override_settings(DEEPSEEK_API_KEY="sk-central-123"):
            router = build_model_router(workspace_id="00000000-0000-0000-0000-000000000000")
        self.assertEqual(router.adapter.api_key, "sk-workspace-999")
