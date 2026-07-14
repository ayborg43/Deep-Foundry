"""
ModelRouter tests against a fake in-memory adapter — isolates capability
negotiation / fallback / logging logic from anything DeepSeek-specific
(that's test_adapter.py's job).
"""

from decimal import Decimal

from django.test import TestCase

from ai.model_router.adapters.base import ModelAdapter
from ai.model_router.errors import AdapterError, CapabilityError, RateLimitedError
from ai.model_router.router import ModelRouter
from ai.model_router.types import (
    Capabilities,
    ChatMessage,
    ModelConfig,
    NormalizedResponse,
    StreamChunk,
    ToolDefinition,
    Usage,
)
from ai.models import ModelCall
from core.models import User, Workspace


class FakeAdapter(ModelAdapter):
    """Configurable in-memory double: models by name, each either a fixed
    response, a queue of stream chunks, or an exception to raise."""

    def __init__(self):
        self.responses: dict[str, NormalizedResponse | Exception] = {}
        self.stream_chunks: dict[str, list[StreamChunk] | Exception] = {}
        self.capabilities_by_model: dict[str, Capabilities] = {}
        self.calls: list[str] = []

    def generate(self, messages, tools, model_config):
        self.calls.append(model_config.model_id)
        if model_config.stream:
            chunks = self.stream_chunks[model_config.model_id]
            if isinstance(chunks, Exception):
                raise chunks
            return iter(chunks)
        result = self.responses[model_config.model_id]
        if isinstance(result, Exception):
            raise result
        return result

    def capabilities(self, model_id):
        default = Capabilities(
            tool_calling=True, max_context=64_000, reasoning_mode=False, streaming=True
        )
        return self.capabilities_by_model.get(model_id, default)

    def estimate_cost(self, usage, model_id):
        return Decimal("0.01")

    def health_check(self):
        return True


class RouterTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="router@example.com", password="x")
        self.workspace = Workspace.objects.create(
            name="Router WS", type=Workspace.WorkspaceType.PERSONAL, owner=self.user
        )
        self.adapter = FakeAdapter()
        self.router = ModelRouter(adapter=self.adapter, workspace_id=self.workspace.id)


class CapabilityNegotiationTests(RouterTestBase):
    def test_rejects_tools_against_non_tool_calling_model(self):
        self.adapter.capabilities_by_model["no-tools"] = Capabilities(
            tool_calling=False, max_context=1000, reasoning_mode=False, streaming=True
        )
        with self.assertRaises(CapabilityError):
            self.router.generate(
                [ChatMessage(role="user", content="hi")],
                [ToolDefinition(name="t", description="d", parameters={})],
                ModelConfig(model_id="no-tools"),
            )
        # Negotiation happens before any network call — nothing logged.
        self.assertEqual(ModelCall.objects.count(), 0)

    def test_allows_tools_against_tool_calling_model(self):
        self.adapter.responses["deepseek-v4-flash"] = NormalizedResponse(
            content="ok", usage=Usage(input_tokens=1, output_tokens=1)
        )
        response = self.router.generate(
            [ChatMessage(role="user", content="hi")],
            [ToolDefinition(name="t", description="d", parameters={})],
            ModelConfig(model_id="deepseek-v4-flash"),
        )
        self.assertEqual(response.content, "ok")


class SuccessLoggingTests(RouterTestBase):
    def test_success_logs_model_call_with_usage_and_cost(self):
        self.adapter.responses["deepseek-v4-flash"] = NormalizedResponse(
            content="hi", usage=Usage(input_tokens=10, output_tokens=20)
        )
        self.router.generate([], [], ModelConfig(model_id="deepseek-v4-flash"))

        call = ModelCall.objects.get()
        self.assertEqual(call.status, ModelCall.Status.SUCCESS)
        self.assertEqual(call.workspace_id, self.workspace.id)
        self.assertEqual(call.model_id, "deepseek-v4-flash")
        self.assertEqual(call.input_tokens, 10)
        self.assertEqual(call.output_tokens, 20)
        self.assertEqual(call.cost_usd, Decimal("0.01"))
        self.assertFalse(call.fallback_used)
        self.assertGreaterEqual(call.latency_ms, 0)


class FallbackTests(RouterTestBase):
    def test_falls_back_on_adapter_error_and_logs_fallback_used(self):
        self.adapter.responses["deepseek-v4-pro"] = AdapterError("degraded")
        self.adapter.responses["deepseek-v4-flash"] = NormalizedResponse(
            content="fallback worked", usage=Usage(input_tokens=5, output_tokens=5)
        )

        response = self.router.generate(
            [], [], ModelConfig(model_id="deepseek-v4-pro"), fallback_model_id="deepseek-v4-flash"
        )

        self.assertEqual(response.content, "fallback worked")
        self.assertEqual(self.adapter.calls, ["deepseek-v4-pro", "deepseek-v4-flash"])

        calls = list(ModelCall.objects.order_by("created_at"))
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].status, ModelCall.Status.ERROR)
        self.assertFalse(calls[0].fallback_used)
        self.assertEqual(calls[1].status, ModelCall.Status.SUCCESS)
        self.assertTrue(calls[1].fallback_used)

    def test_falls_back_on_rate_limit(self):
        self.adapter.responses["deepseek-v4-pro"] = RateLimitedError("slow down")
        self.adapter.responses["deepseek-v4-flash"] = NormalizedResponse(content="ok", usage=None)

        self.router.generate(
            [], [], ModelConfig(model_id="deepseek-v4-pro"), fallback_model_id="deepseek-v4-flash"
        )
        first_call = ModelCall.objects.order_by("created_at").first()
        self.assertEqual(first_call.status, ModelCall.Status.RATE_LIMITED)

    def test_no_fallback_configured_raises_and_logs_error(self):
        self.adapter.responses["deepseek-v4-pro"] = AdapterError("down")
        with self.assertRaises(AdapterError):
            self.router.generate([], [], ModelConfig(model_id="deepseek-v4-pro"))
        call = ModelCall.objects.get()
        self.assertEqual(call.status, ModelCall.Status.ERROR)

    def test_fallback_also_fails_raises_original_chained(self):
        self.adapter.responses["deepseek-v4-pro"] = AdapterError("primary down")
        self.adapter.responses["deepseek-v4-flash"] = AdapterError("fallback also down")
        with self.assertRaises(AdapterError) as ctx:
            self.router.generate(
                [], [], ModelConfig(model_id="deepseek-v4-pro"), fallback_model_id="deepseek-v4-flash"
            )
        self.assertEqual(str(ctx.exception), "fallback also down")
        self.assertEqual(ModelCall.objects.count(), 2)


class StreamingTests(RouterTestBase):
    def test_stream_yields_chunks_and_logs_after_completion(self):
        self.adapter.stream_chunks["deepseek-v4-flash"] = [
            StreamChunk(delta="Hel"),
            StreamChunk(
                delta="lo", finish_reason="stop", usage=Usage(input_tokens=2, output_tokens=2)
            ),
        ]
        stream_config = ModelConfig(model_id="deepseek-v4-flash", stream=True)
        chunks = list(self.router.generate_stream([], [], stream_config))
        self.assertEqual([c.delta for c in chunks], ["Hel", "lo"])
        call = ModelCall.objects.get()
        self.assertEqual(call.status, ModelCall.Status.SUCCESS)
        self.assertEqual(call.input_tokens, 2)

    def test_stream_error_logs_failure_and_reraises(self):
        self.adapter.stream_chunks["deepseek-v4-flash"] = AdapterError("stream broke")
        stream_config = ModelConfig(model_id="deepseek-v4-flash", stream=True)
        with self.assertRaises(AdapterError):
            list(self.router.generate_stream([], [], stream_config))
        call = ModelCall.objects.get()
        self.assertEqual(call.status, ModelCall.Status.ERROR)

    def test_generate_forces_non_streaming_even_if_config_says_stream(self):
        self.adapter.responses["deepseek-v4-flash"] = NormalizedResponse(content="sync", usage=None)
        response = self.router.generate(
            [], [], ModelConfig(model_id="deepseek-v4-flash", stream=True)
        )
        self.assertEqual(response.content, "sync")
