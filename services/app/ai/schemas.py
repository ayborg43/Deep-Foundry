"""Pydantic request/response schemas for the AI modules' HTTP surface."""

from pydantic import BaseModel, Field


class ChatMessageIn(BaseModel):
    role: str
    content: str
    tool_call_id: str | None = None
    name: str | None = None


class ToolDefinitionIn(BaseModel):
    name: str
    description: str
    parameters: dict = Field(default_factory=dict)


class GenerateRequest(BaseModel):
    workspace_id: str
    model_id: str
    messages: list[ChatMessageIn]
    tools: list[ToolDefinitionIn] = Field(default_factory=list)
    temperature: float = 1.0
    max_tokens: int | None = None
    fallback_model_id: str | None = None


class ToolCallOut(BaseModel):
    id: str
    name: str
    arguments: dict


class UsageOut(BaseModel):
    input_tokens: int
    output_tokens: int


class GenerateResponse(BaseModel):
    content: str
    tool_calls: list[ToolCallOut]
    usage: UsageOut | None
    model_id: str
    finish_reason: str
