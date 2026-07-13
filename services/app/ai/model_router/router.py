"""
The Model Router — the single internal interface every module uses to reach
DeepSeek, per SOUL.md §16.1/§16.3 and ARCHITECTURE.md §5. Owns capability
negotiation, the fallback chain, and per-call logging to `model_calls`;
never talks to DeepSeek directly (that's the adapter's job).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING

from ai.model_router.adapters.base import ModelAdapter
from ai.model_router.errors import AdapterError, CapabilityError, RateLimitedError
from ai.model_router.types import (
    ChatMessage,
    ModelConfig,
    NormalizedResponse,
    StreamChunk,
    ToolDefinition,
    Usage,
)
from ai.models import ModelCall

if TYPE_CHECKING:
    from uuid import UUID


class ModelRouter:
    def __init__(
        self,
        adapter: ModelAdapter,
        workspace_id: "UUID | str",
        coworker_id: "UUID | str | None" = None,
    ):
        self.adapter = adapter
        self.workspace_id = workspace_id
        self.coworker_id = coworker_id

    def generate(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition],
        model_config: ModelConfig,
        fallback_model_id: str | None = None,
    ) -> NormalizedResponse:
        """Non-streaming path. Raises CapabilityError before any network call
        if the requested model can't do what's being asked; retries once
        against fallback_model_id on adapter failure/rate-limit."""
        if model_config.stream:
            # This method always returns NormalizedResponse — callers who
            # want a stream must use generate_stream(). Force it rather than
            # silently handing back an iterator where a response is typed.
            model_config = ModelConfig(
                model_id=model_config.model_id,
                temperature=model_config.temperature,
                max_tokens=model_config.max_tokens,
                stream=False,
            )
        self._negotiate(tools, model_config)
        request_id = uuid.uuid4()

        try:
            response, latency_ms = self._call_sync(messages, tools, model_config)
            self._log(
                request_id, model_config, tools, latency_ms, ModelCall.Status.SUCCESS,
                usage=response.usage, fallback_used=False,
            )
            return response
        except (AdapterError, RateLimitedError) as primary_error:
            self._log_failure(request_id, model_config, tools, primary_error, fallback_used=False)
            if not fallback_model_id:
                raise

            fallback_config = ModelConfig(
                model_id=fallback_model_id,
                temperature=model_config.temperature,
                max_tokens=model_config.max_tokens,
                stream=model_config.stream,
            )
            try:
                response, latency_ms = self._call_sync(messages, tools, fallback_config)
                self._log(
                    request_id, fallback_config, tools, latency_ms, ModelCall.Status.SUCCESS,
                    usage=response.usage, fallback_used=True,
                )
                return response
            except (AdapterError, RateLimitedError) as fallback_error:
                self._log_failure(
                    request_id, fallback_config, tools, fallback_error, fallback_used=True
                )
                raise fallback_error from primary_error

    def generate_stream(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition],
        model_config: ModelConfig,
    ) -> Iterator[StreamChunk]:
        """Streaming path. No fallback — once bytes have started reaching the
        client, silently swapping models mid-stream would be incoherent,
        per ARCHITECTURE.md §5's normalization goal. A stream failure is
        logged as an error and re-raised for the caller to surface."""
        if not model_config.stream:
            model_config = ModelConfig(
                model_id=model_config.model_id,
                temperature=model_config.temperature,
                max_tokens=model_config.max_tokens,
                stream=True,
            )
        self._negotiate(tools, model_config)
        request_id = uuid.uuid4()
        start = time.monotonic()
        final_usage: Usage | None = None

        try:
            for chunk in self.adapter.generate(messages, tools, model_config):
                if chunk.usage:
                    final_usage = chunk.usage
                yield chunk
        except (AdapterError, RateLimitedError) as error:
            self._log_failure(request_id, model_config, tools, error, fallback_used=False)
            raise
        else:
            latency_ms = int((time.monotonic() - start) * 1000)
            self._log(
                request_id, model_config, tools, latency_ms, ModelCall.Status.SUCCESS,
                usage=final_usage, fallback_used=False,
            )

    # -- internals ---------------------------------------------------------

    def _negotiate(self, tools: Sequence[ToolDefinition], model_config: ModelConfig) -> None:
        capabilities = self.adapter.capabilities(model_config.model_id)
        if tools and not capabilities.tool_calling:
            raise CapabilityError(
                f"{model_config.model_id} does not support tool calling, "
                f"but {len(tools)} tool(s) were requested."
            )
        if model_config.stream and not capabilities.streaming:
            raise CapabilityError(f"{model_config.model_id} does not support streaming.")

    def _call_sync(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition],
        model_config: ModelConfig,
    ) -> tuple[NormalizedResponse, int]:
        start = time.monotonic()
        response = self.adapter.generate(messages, tools, model_config)
        latency_ms = int((time.monotonic() - start) * 1000)
        return response, latency_ms

    def _log(
        self,
        request_id: uuid.UUID,
        model_config: ModelConfig,
        tools: Sequence[ToolDefinition],
        latency_ms: int,
        status: str,
        usage: Usage | None,
        fallback_used: bool,
    ) -> None:
        cost = self.adapter.estimate_cost(usage, model_config.model_id) if usage else None
        ModelCall.objects.create(
            request_id=request_id,
            workspace_id=self.workspace_id,
            coworker_id=self.coworker_id,
            deployment_mode="deepseek_cloud",
            model_id=model_config.model_id,
            capability_requested={"tool_calling": bool(tools), "streaming": model_config.stream},
            fallback_used=fallback_used,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            cost_usd=cost,
            latency_ms=latency_ms,
            status=status,
        )

    def _log_failure(
        self,
        request_id: uuid.UUID,
        model_config: ModelConfig,
        tools: Sequence[ToolDefinition],
        error: Exception,
        fallback_used: bool,
    ) -> None:
        status = (
            ModelCall.Status.RATE_LIMITED
            if isinstance(error, RateLimitedError)
            else ModelCall.Status.ERROR
        )
        ModelCall.objects.create(
            request_id=request_id,
            workspace_id=self.workspace_id,
            coworker_id=self.coworker_id,
            deployment_mode="deepseek_cloud",
            model_id=model_config.model_id,
            capability_requested={"tool_calling": bool(tools), "streaming": model_config.stream},
            fallback_used=fallback_used,
            latency_ms=0,
            status=status,
        )
