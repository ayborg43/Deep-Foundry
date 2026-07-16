from __future__ import annotations

from django.conf import settings

from ai.model_router.adapters.deepseek_cloud import DeepSeekCloudAdapter
from ai.model_router.adapters.deepseek_self_hosted import DeepSeekSelfHostedAdapter
from ai.model_router.router import ModelRouter
from core.interface import CredentialNotFoundError, get_provider_credential


def build_model_router(*, workspace_id, coworker_id=None, model_binding: dict | None = None):
    binding = model_binding or {}
    mode = binding.get("deployment_mode", "deepseek_cloud")
    try:
        credential = get_provider_credential(workspace_id, mode)
    except CredentialNotFoundError:
        credential = None

    if mode == "deepseek_self_hosted":
        if credential is None or not credential.endpoint_url:
            raise ValueError("Self-hosted DeepSeek credentials require an endpoint URL.")
        adapter = DeepSeekSelfHostedAdapter(credential.endpoint_url, credential.api_key)
    else:
        # Workspace-specific key wins; otherwise fall back to the instance-wide
        # DEEPSEEK_API_KEY so one key can serve the whole self-hosted deployment.
        api_key = (credential.api_key if credential else None) or settings.DEEPSEEK_API_KEY
        if not api_key:
            raise CredentialNotFoundError(
                "No DeepSeek Cloud API key is available — add one under Model providers, "
                "or set DEEPSEEK_API_KEY on the server."
            )
        adapter = DeepSeekCloudAdapter(api_key)
    return ModelRouter(adapter=adapter, workspace_id=workspace_id, coworker_id=coworker_id)
