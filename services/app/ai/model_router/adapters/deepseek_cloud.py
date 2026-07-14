"""
DeepSeek Cloud API adapter — the one active adapter for MVP, per SOUL.md
§16.2. DeepSeek's API is OpenAI-compatible (chat completions shape), so this
talks to it with stdlib `urllib` rather than adding an SDK dependency —
consistent with how core/google_oauth.py handles Google's API.

Every network call is isolated in a small method (`_post`, `_post_stream`,
`_get`) specifically so tests can monkeypatch them without a real DeepSeek
API key — there is no key available in this environment, so nothing here has
been verified against the live API; only the normalization logic around
these calls is tested.
"""

import json
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from decimal import Decimal

from ai.model_router.adapters.base import ModelAdapter
from ai.model_router.errors import AdapterError, RateLimitedError
from ai.model_router.types import (
    Capabilities,
    ChatMessage,
    GenerateResult,
    ModelConfig,
    NormalizedResponse,
    StreamChunk,
    ToolCall,
    ToolDefinition,
    Usage,
)

API_BASE = "https://api.deepseek.com/v1"

# DeepSeek 4 — the single MVP-relevant model, replacing the earlier
# deepseek-chat/deepseek-reasoner pair. PLACEHOLDER values: the real
# model_id string DeepSeek's API expects, its context window, and its
# per-million-token pricing haven't been confirmed against DeepSeek's
# published docs yet — re-check all three before relying on this for real
# capability negotiation or billing.
_MODEL_CAPABILITIES = {
    "deepseek-4": Capabilities(
        tool_calling=True, max_context=128_000, reasoning_mode=True, streaming=True
    ),
}

_PRICE_PER_MILLION_TOKENS_USD = {
    "deepseek-4": {"input": Decimal("0.55"), "output": Decimal("2.19")},
}


class DeepSeekCloudAdapter(ModelAdapter):
    deployment_mode = "deepseek_cloud"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_base = API_BASE

    # -- ModelAdapter contract -------------------------------------------------

    def generate(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition],
        model_config: ModelConfig,
    ) -> GenerateResult:
        payload = self._build_payload(messages, tools, model_config)
        if model_config.stream:
            return self._generate_stream(payload)
        return self._generate_sync(payload)

    def capabilities(self, model_id: str) -> Capabilities:
        if model_id not in _MODEL_CAPABILITIES:
            raise AdapterError(f"Unknown DeepSeek model_id: {model_id!r}")
        return _MODEL_CAPABILITIES[model_id]

    def estimate_cost(self, usage: Usage, model_id: str) -> Decimal:
        prices = _PRICE_PER_MILLION_TOKENS_USD.get(model_id)
        if prices is None:
            return Decimal("0")
        input_cost = (Decimal(usage.input_tokens) / Decimal(1_000_000)) * prices["input"]
        output_cost = (Decimal(usage.output_tokens) / Decimal(1_000_000)) * prices["output"]
        return (input_cost + output_cost).quantize(Decimal("0.000001"))

    def health_check(self) -> bool:
        try:
            self._get("/models")
            return True
        except AdapterError:
            return False

    # -- request building / normalization --------------------------------------

    def _build_payload(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition],
        model_config: ModelConfig,
    ) -> dict:
        payload: dict = {
            "model": model_config.model_id,
            "messages": [self._message_to_wire(m) for m in messages],
            "temperature": model_config.temperature,
            "stream": model_config.stream,
        }
        if model_config.max_tokens is not None:
            payload["max_tokens"] = model_config.max_tokens
        if tools:
            payload["tools"] = [self._tool_to_wire(t) for t in tools]
        return payload

    @staticmethod
    def _message_to_wire(message: ChatMessage) -> dict:
        wire: dict = {"role": message.role, "content": message.content}
        if message.tool_call_id:
            wire["tool_call_id"] = message.tool_call_id
        if message.name:
            wire["name"] = message.name
        if message.tool_calls:
            wire["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                }
                for tc in message.tool_calls
            ]
        return wire

    @staticmethod
    def _tool_to_wire(tool: ToolDefinition) -> dict:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

    def _generate_sync(self, payload: dict) -> NormalizedResponse:
        response = self._post("/chat/completions", payload)
        choice = response["choices"][0]
        message = choice["message"]
        usage_raw = response.get("usage") or {}
        return NormalizedResponse(
            content=message.get("content") or "",
            tool_calls=[self._tool_call_from_wire(tc) for tc in message.get("tool_calls") or []],
            usage=Usage(
                input_tokens=usage_raw.get("prompt_tokens", 0),
                output_tokens=usage_raw.get("completion_tokens", 0),
            ),
            model_id=response.get("model", payload["model"]),
            finish_reason=choice.get("finish_reason") or "stop",
        )

    @staticmethod
    def _tool_call_from_wire(raw: dict) -> ToolCall:
        function = raw.get("function", {})
        arguments = function.get("arguments", "{}")
        try:
            parsed_arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
        except json.JSONDecodeError:
            parsed_arguments = {}
        return ToolCall(
            id=raw.get("id", ""), name=function.get("name", ""), arguments=parsed_arguments
        )

    def _generate_stream(self, payload: dict) -> Iterator[StreamChunk]:
        # DeepSeek's streaming API sends tool_calls as fragments across many
        # chunks, keyed by `index` — id/name arrive on the first fragment for
        # that index, `arguments` arrives as a partial JSON string split
        # across subsequent fragments. Accumulate silently and only surface
        # the finalized ToolCall list on the chunk carrying finish_reason.
        accumulated: dict[int, dict] = {}
        for event in self._post_stream("/chat/completions", payload):
            if not event.get("choices"):
                continue
            choice = event["choices"][0]
            delta = choice.get("delta", {})
            finish_reason = choice.get("finish_reason")
            usage_raw = event.get("usage")

            for fragment in delta.get("tool_calls") or []:
                index = fragment.get("index", 0)
                slot = accumulated.setdefault(index, {"id": "", "name": "", "arguments": ""})
                if fragment.get("id"):
                    slot["id"] = fragment["id"]
                function = fragment.get("function") or {}
                if function.get("name"):
                    slot["name"] = function["name"]
                if function.get("arguments"):
                    slot["arguments"] += function["arguments"]

            content = delta.get("content") or ""
            if not content and finish_reason is None and not usage_raw:
                # A pure tool-call-fragment chunk — nothing complete to
                # surface yet, already accumulated above.
                continue

            yield StreamChunk(
                delta=content,
                finish_reason=finish_reason,
                usage=(
                    Usage(
                        input_tokens=usage_raw.get("prompt_tokens", 0),
                        output_tokens=usage_raw.get("completion_tokens", 0),
                    )
                    if usage_raw
                    else None
                ),
                tool_calls=self._finalize_tool_calls(accumulated) if accumulated else None,
            )

    @staticmethod
    def _finalize_tool_calls(accumulated: dict[int, dict]) -> list[ToolCall]:
        tool_calls = []
        for index in sorted(accumulated):
            slot = accumulated[index]
            arguments = slot["arguments"]
            try:
                parsed_arguments = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError:
                parsed_arguments = {}
            tool_calls.append(
                ToolCall(id=slot["id"], name=slot["name"], arguments=parsed_arguments)
            )
        return tool_calls

    # -- network boundary (isolated for mocking) --------------------------------

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_post_request(self, path: str, payload: dict) -> urllib.request.Request:
        return urllib.request.Request(
            f"{self.api_base}{path}",
            data=json.dumps(payload).encode(),
            headers=self._headers(),
            method="POST",
        )

    def _post(self, path: str, payload: dict) -> dict:
        request = self._build_post_request(path, payload)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            body = exc.read()
            if exc.code == 429:
                raise RateLimitedError(f"DeepSeek rate limited: {body}") from exc
            raise AdapterError(f"DeepSeek API error {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise AdapterError(f"DeepSeek unreachable: {exc.reason}") from exc

    def _post_stream(self, path: str, payload: dict) -> Iterator[dict]:
        request = self._build_post_request(path, payload)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                for raw_line in response:
                    line = raw_line.decode().strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        return
                    yield json.loads(data)
        except urllib.error.HTTPError as exc:
            body = exc.read()
            if exc.code == 429:
                raise RateLimitedError(f"DeepSeek rate limited: {body}") from exc
            raise AdapterError(f"DeepSeek API error {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise AdapterError(f"DeepSeek unreachable: {exc.reason}") from exc

    def _get(self, path: str) -> dict:
        request = urllib.request.Request(f"{self.api_base}{path}", headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read())
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            raise AdapterError(f"DeepSeek health check failed: {exc}") from exc
