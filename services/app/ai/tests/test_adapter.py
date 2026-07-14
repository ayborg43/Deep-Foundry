"""
Unit tests for DeepSeekCloudAdapter. No real DeepSeek API key exists in this
environment, so every test mocks the adapter's network boundary
(_post/_post_stream/_get) — these verify the normalization logic is correct
against DeepSeek's documented (OpenAI-compatible) response shape, not that
the live API actually behaves that way. Flagged in the Milestone 2 report.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase

from ai.model_router.adapters.deepseek_cloud import DeepSeekCloudAdapter
from ai.model_router.errors import AdapterError, RateLimitedError
from ai.model_router.types import ChatMessage, ModelConfig, ToolDefinition, Usage


def _raw_response(content="Hello!", tool_calls=None, finish_reason="stop"):
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "id": "chatcmpl-123",
        "model": "deepseek-v4-flash",
        "choices": [{"message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


class GenerateSyncTests(SimpleTestCase):
    def setUp(self):
        self.adapter = DeepSeekCloudAdapter(api_key="test-key")

    @patch.object(DeepSeekCloudAdapter, "_post")
    def test_normalizes_simple_response(self, mock_post):
        mock_post.return_value = _raw_response(content="Hi there")
        response = self.adapter.generate(
            [ChatMessage(role="user", content="hi")], [], ModelConfig(model_id="deepseek-v4-flash")
        )
        self.assertEqual(response.content, "Hi there")
        self.assertEqual(response.usage.input_tokens, 10)
        self.assertEqual(response.usage.output_tokens, 5)
        self.assertEqual(response.finish_reason, "stop")
        self.assertEqual(response.tool_calls, [])

    @patch.object(DeepSeekCloudAdapter, "_post")
    def test_normalizes_tool_calls(self, mock_post):
        mock_post.return_value = _raw_response(
            content="",
            tool_calls=[
                {
                    "id": "call_1",
                    "function": {"name": "get_weather", "arguments": '{"city": "Lagos"}'},
                }
            ],
            finish_reason="tool_calls",
        )
        response = self.adapter.generate(
            [ChatMessage(role="user", content="weather?")],
            [ToolDefinition(name="get_weather", description="", parameters={})],
            ModelConfig(model_id="deepseek-v4-flash"),
        )
        self.assertEqual(len(response.tool_calls), 1)
        self.assertEqual(response.tool_calls[0].name, "get_weather")
        self.assertEqual(response.tool_calls[0].arguments, {"city": "Lagos"})
        self.assertEqual(response.finish_reason, "tool_calls")

    @patch.object(DeepSeekCloudAdapter, "_post")
    def test_malformed_tool_arguments_do_not_crash(self, mock_post):
        mock_post.return_value = _raw_response(
            content="",
            tool_calls=[{"id": "call_1", "function": {"name": "x", "arguments": "not json"}}],
        )
        response = self.adapter.generate(
            [ChatMessage(role="user", content="x")], [], ModelConfig(model_id="deepseek-v4-flash")
        )
        self.assertEqual(response.tool_calls[0].arguments, {})

    @patch.object(DeepSeekCloudAdapter, "_post")
    def test_sends_correct_payload_shape(self, mock_post):
        mock_post.return_value = _raw_response()
        self.adapter.generate(
            [ChatMessage(role="system", content="be nice"), ChatMessage(role="user", content="hi")],
            [ToolDefinition(name="t", description="d", parameters={"type": "object"})],
            ModelConfig(model_id="deepseek-v4-pro", temperature=0.5, max_tokens=100),
        )
        sent_path, sent_payload = mock_post.call_args[0]
        self.assertEqual(sent_path, "/chat/completions")
        self.assertEqual(sent_payload["model"], "deepseek-v4-pro")
        self.assertEqual(sent_payload["temperature"], 0.5)
        self.assertEqual(sent_payload["max_tokens"], 100)
        self.assertEqual(sent_payload["stream"], False)
        self.assertEqual(len(sent_payload["messages"]), 2)
        self.assertEqual(sent_payload["tools"][0]["function"]["name"], "t")


class GenerateStreamTests(SimpleTestCase):
    def setUp(self):
        self.adapter = DeepSeekCloudAdapter(api_key="test-key")

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_normalizes_stream_chunks(self, mock_stream):
        mock_stream.return_value = iter(
            [
                {"choices": [{"delta": {"content": "Hel"}, "finish_reason": None}]},
                {"choices": [{"delta": {"content": "lo"}, "finish_reason": None}]},
                {
                    "choices": [{"delta": {}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2},
                },
            ]
        )
        chunks = list(
            self.adapter.generate(
                [ChatMessage(role="user", content="hi")],
                [],
                ModelConfig(model_id="deepseek-v4-flash", stream=True),
            )
        )
        self.assertEqual([c.delta for c in chunks], ["Hel", "lo", ""])
        self.assertIsNone(chunks[0].finish_reason)
        self.assertEqual(chunks[2].finish_reason, "stop")
        self.assertEqual(chunks[2].usage.input_tokens, 3)
        self.assertIsNone(chunks[2].tool_calls)

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_accumulates_fragmented_tool_call_across_chunks(self, mock_stream):
        mock_stream.return_value = iter(
            [
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {"name": "get_weather", "arguments": ""},
                                    }
                                ]
                            },
                            "finish_reason": None,
                        }
                    ]
                },
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [{"index": 0, "function": {"arguments": '{"city"'}}]
                            },
                            "finish_reason": None,
                        }
                    ]
                },
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {"index": 0, "function": {"arguments": ': "Lagos"}'}}
                                ]
                            },
                            "finish_reason": None,
                        }
                    ]
                },
                {
                    "choices": [{"delta": {}, "finish_reason": "tool_calls"}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 3},
                },
            ]
        )
        chunks = list(
            self.adapter.generate(
                [ChatMessage(role="user", content="weather?")],
                [ToolDefinition(name="get_weather", description="", parameters={})],
                ModelConfig(model_id="deepseek-v4-flash", stream=True),
            )
        )
        # The three fragment-only chunks carry nothing complete to surface —
        # only the finish_reason chunk yields, with the fully assembled call.
        self.assertEqual(len(chunks), 1)
        final = chunks[0]
        self.assertEqual(final.finish_reason, "tool_calls")
        self.assertEqual(len(final.tool_calls), 1)
        self.assertEqual(final.tool_calls[0].id, "call_1")
        self.assertEqual(final.tool_calls[0].name, "get_weather")
        self.assertEqual(final.tool_calls[0].arguments, {"city": "Lagos"})

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_accumulates_two_parallel_tool_calls_by_index(self, mock_stream):
        mock_stream.return_value = iter(
            [
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_1",
                                        "function": {"name": "get_weather", "arguments": '{"a":1}'},
                                    },
                                    {
                                        "index": 1,
                                        "id": "call_2",
                                        "function": {"name": "get_time", "arguments": '{"b":2}'},
                                    },
                                ]
                            },
                            "finish_reason": None,
                        }
                    ]
                },
                {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
            ]
        )
        chunks = list(
            self.adapter.generate(
                [ChatMessage(role="user", content="x")],
                [],
                ModelConfig(model_id="deepseek-v4-flash", stream=True),
            )
        )
        self.assertEqual(len(chunks), 1)
        names = [tc.name for tc in chunks[0].tool_calls]
        self.assertEqual(names, ["get_weather", "get_time"])

    @patch.object(DeepSeekCloudAdapter, "_post_stream")
    def test_malformed_streamed_tool_arguments_do_not_crash(self, mock_stream):
        mock_stream.return_value = iter(
            [
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_1",
                                        "function": {"name": "x", "arguments": "not json"},
                                    }
                                ]
                            },
                            "finish_reason": None,
                        }
                    ]
                },
                {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
            ]
        )
        chunks = list(
            self.adapter.generate(
                [ChatMessage(role="user", content="x")],
                [],
                ModelConfig(model_id="deepseek-v4-flash", stream=True),
            )
        )
        self.assertEqual(chunks[0].tool_calls[0].arguments, {})


class ErrorHandlingTests(SimpleTestCase):
    def setUp(self):
        self.adapter = DeepSeekCloudAdapter(api_key="test-key")

    @patch.object(DeepSeekCloudAdapter, "_post")
    def test_adapter_error_propagates(self, mock_post):
        mock_post.side_effect = AdapterError("boom")
        with self.assertRaises(AdapterError):
            self.adapter.generate(
                [ChatMessage(role="user", content="x")], [], ModelConfig(model_id="deepseek-v4-flash")
            )

    @patch.object(DeepSeekCloudAdapter, "_post")
    def test_rate_limit_error_propagates(self, mock_post):
        mock_post.side_effect = RateLimitedError("slow down")
        with self.assertRaises(RateLimitedError):
            self.adapter.generate(
                [ChatMessage(role="user", content="x")], [], ModelConfig(model_id="deepseek-v4-flash")
            )


class CapabilitiesAndCostTests(SimpleTestCase):
    def setUp(self):
        self.adapter = DeepSeekCloudAdapter(api_key="test-key")

    def test_flash_model_capabilities(self):
        caps = self.adapter.capabilities("deepseek-v4-flash")
        self.assertTrue(caps.tool_calling)
        self.assertTrue(caps.reasoning_mode)

    def test_pro_model_capabilities(self):
        caps = self.adapter.capabilities("deepseek-v4-pro")
        self.assertTrue(caps.tool_calling)
        self.assertTrue(caps.reasoning_mode)

    def test_v4_models_are_available_for_selection(self):
        for model_id in ("deepseek-v4-flash", "deepseek-v4-pro"):
            with self.subTest(model_id=model_id):
                caps = self.adapter.capabilities(model_id)
                self.assertTrue(caps.tool_calling)
                self.assertTrue(caps.reasoning_mode)
                self.assertTrue(caps.streaming)

    def test_unknown_model_raises(self):
        with self.assertRaises(AdapterError):
            self.adapter.capabilities("gpt-4")

    def test_estimate_cost_matches_hand_calculation(self):
        usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)
        cost = self.adapter.estimate_cost(usage, "deepseek-v4-flash")
        self.assertEqual(cost, Decimal("0.14") + Decimal("0.28"))

    def test_estimate_cost_zero_for_unknown_model(self):
        usage = Usage(input_tokens=100, output_tokens=100)
        self.assertEqual(self.adapter.estimate_cost(usage, "unknown"), Decimal("0"))


class HealthCheckTests(SimpleTestCase):
    def setUp(self):
        self.adapter = DeepSeekCloudAdapter(api_key="test-key")

    @patch.object(DeepSeekCloudAdapter, "_get")
    def test_health_check_true_on_success(self, mock_get):
        mock_get.return_value = {"data": []}
        self.assertTrue(self.adapter.health_check())

    @patch.object(DeepSeekCloudAdapter, "_get")
    def test_health_check_false_on_failure(self, mock_get):
        mock_get.side_effect = AdapterError("unreachable")
        self.assertFalse(self.adapter.health_check())
