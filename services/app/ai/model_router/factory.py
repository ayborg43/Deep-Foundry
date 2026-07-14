from __future__ import annotations

from ai.model_router.adapters.deepseek_cloud import DeepSeekCloudAdapter
from ai.model_router.adapters.deepseek_self_hosted import DeepSeekSelfHostedAdapter
from ai.model_router.router import ModelRouter
from core.interface import get_provider_credential


def build_model_router(*, workspace_id, coworker_id=None, model_binding: dict | None = None):
    binding = model_binding or {}
    mode = binding.get("deployment_mode", "deepseek_cloud")
    credential = get_provider_credential(workspace_id, mode)
    if mode == "deepseek_self_hosted":
        if not credential.endpoint_url:
            raise ValueError("Self-hosted DeepSeek credentials require an endpoint URL.")
        adapter = DeepSeekSelfHostedAdapter(credential.endpoint_url, credential.api_key)
    else:
        if not credential.api_key:
            raise ValueError("Stored DeepSeek Cloud credential has no usable API key.")
        adapter = DeepSeekCloudAdapter(credential.api_key)
    return ModelRouter(adapter=adapter, workspace_id=workspace_id, coworker_id=coworker_id)
