"""
Normalized request/response schema for the Model Router, per ARCHITECTURE.md
§5. Every adapter speaks these types — never a provider's raw wire format —
so a Skill's tool definitions, and anything else upstream of the Router,
never need to know which deployment mode (or, once it exists, which of
DeepSeek Cloud vs. self-hosted) is actually serving a request.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str
    tool_call_id: str | None = None  # set on role="tool" messages
    name: str | None = None
    # Set on role="assistant" messages that requested tool calls, so a
    # follow-up model call replaying history sees what it asked for, not
    # just the tool results that came back.
    tool_calls: list[ToolCall] | None = None


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema for the tool's arguments


@dataclass(frozen=True)
class ModelConfig:
    model_id: str  # e.g. "deepseek-4"
    temperature: float = 1.0
    max_tokens: int | None = None
    stream: bool = False


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class NormalizedResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage | None = None
    model_id: str = ""
    finish_reason: str = "stop"


@dataclass(frozen=True)
class StreamChunk:
    delta: str
    finish_reason: str | None = None
    usage: Usage | None = None  # only populated on the final chunk
    # Only populated once, alongside finish_reason=="tool_calls" — providers
    # stream tool-call arguments as fragmented deltas across many chunks
    # (accumulated by index), so a single chunk's raw fragment is never
    # valid on its own; adapters emit the fully-assembled list here instead
    # of leaking partial fragments to callers.
    tool_calls: list[ToolCall] | None = None


@dataclass(frozen=True)
class Capabilities:
    tool_calling: bool
    max_context: int
    reasoning_mode: bool
    streaming: bool


GenerateResult = NormalizedResponse | Iterator[StreamChunk]
