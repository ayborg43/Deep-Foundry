from __future__ import annotations

from decimal import Decimal

from ai.model_router.adapters.deepseek_cloud import DeepSeekCloudAdapter
from ai.model_router.types import Capabilities, Usage


class DeepSeekSelfHostedAdapter(DeepSeekCloudAdapter):
    """OpenAI-compatible local DeepSeek endpoint (vLLM/Ollama-style)."""

    deployment_mode = "deepseek_self_hosted"

    def __init__(self, endpoint_url: str, api_key: str | None = None):
        super().__init__(api_key=api_key or "")
        self.api_base = endpoint_url.rstrip("/")

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def capabilities(self, model_id: str) -> Capabilities:
        return Capabilities(
            tool_calling=True,
            max_context=64_000,
            reasoning_mode=("reason" in model_id.lower() or "r1" in model_id.lower()),
            streaming=True,
        )

    def estimate_cost(self, usage: Usage, model_id: str) -> Decimal:
        return Decimal("0")
