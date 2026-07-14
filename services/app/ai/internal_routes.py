"""
Internal test-harness endpoints for the Model Router, per
IMPLEMENTATION_PLAN.md Milestone 2's exit criteria and Epic 2.3 (SSE
streaming through the real ASGI mount). Not the product chat API — that's
Milestone 4, once Coworkers exist. Documented as an internal/dev surface in
API.md, superseded (not necessarily removed) once real chat endpoints land.
"""

import json

from asgiref.sync import sync_to_async
from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import StreamingResponse

from ai.async_utils import async_iter_from_sync, close_django_connections
from ai.dependencies import get_current_user, require_workspace_member
from ai.model_router.adapters.deepseek_cloud import DeepSeekCloudAdapter
from ai.model_router.errors import AdapterError, CapabilityError, RateLimitedError
from ai.model_router.router import ModelRouter
from ai.model_router.types import ChatMessage, ModelConfig, ToolDefinition
from ai.schemas import GenerateRequest, GenerateResponse, ToolCallOut, UsageOut
from core.interface import CredentialNotFoundError, get_provider_credential
from core.models import User

router = APIRouter(prefix="/internal", tags=["internal-test-harness"])


async def _build_router(workspace_id: str, user: User) -> ModelRouter:
    await require_workspace_member(workspace_id, user)
    try:
        credential = await sync_to_async(get_provider_credential)(workspace_id, "deepseek_cloud")
    except CredentialNotFoundError as exc:
        raise HTTPException(
            status_code=424,
            detail=f"No DeepSeek Cloud credential configured for this workspace: {exc}",
        ) from exc
    if not credential.api_key:
        raise HTTPException(status_code=424, detail="Stored credential has no usable API key.")
    adapter = DeepSeekCloudAdapter(api_key=credential.api_key)
    return ModelRouter(adapter=adapter, workspace_id=workspace_id)


def _to_messages(payload: GenerateRequest) -> list[ChatMessage]:
    return [
        ChatMessage(role=m.role, content=m.content, tool_call_id=m.tool_call_id, name=m.name)
        for m in payload.messages
    ]


def _to_tools(payload: GenerateRequest) -> list[ToolDefinition]:
    return [
        ToolDefinition(name=t.name, description=t.description, parameters=t.parameters)
        for t in payload.tools
    ]


def _model_config(payload: GenerateRequest, *, stream: bool) -> ModelConfig:
    return ModelConfig(
        model_id=payload.model_id,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        stream=stream,
    )


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    payload: GenerateRequest, user: User = Depends(get_current_user)
) -> GenerateResponse:
    model_router = await _build_router(payload.workspace_id, user)
    messages, tools = _to_messages(payload), _to_tools(payload)
    model_config = _model_config(payload, stream=False)

    try:
        response = await sync_to_async(model_router.generate)(
            messages, tools, model_config, payload.fallback_model_id
        )
    except CapabilityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RateLimitedError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except AdapterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await close_django_connections()

    return GenerateResponse(
        content=response.content,
        tool_calls=[
            ToolCallOut(id=tc.id, name=tc.name, arguments=tc.arguments)
            for tc in response.tool_calls
        ],
        usage=(
            UsageOut(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
            if response.usage
            else None
        ),
        model_id=response.model_id,
        finish_reason=response.finish_reason,
    )


@router.post("/generate/stream")
async def generate_stream(payload: GenerateRequest, user: User = Depends(get_current_user)):
    model_router = await _build_router(payload.workspace_id, user)
    messages, tools = _to_messages(payload), _to_tools(payload)
    model_config = _model_config(payload, stream=True)

    try:
        sync_stream = model_router.generate_stream(messages, tools, model_config)
    except CapabilityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    def _sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    async def event_source():
        try:
            async for chunk in async_iter_from_sync(sync_stream):
                yield _sse(
                    "chunk",
                    {
                        "delta": chunk.delta,
                        "finish_reason": chunk.finish_reason,
                        "usage": (
                            {
                                "input_tokens": chunk.usage.input_tokens,
                                "output_tokens": chunk.usage.output_tokens,
                            }
                            if chunk.usage
                            else None
                        ),
                        "tool_calls": (
                            [
                                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                                for tc in chunk.tool_calls
                            ]
                            if chunk.tool_calls is not None
                            else None
                        ),
                    },
                )
        except (AdapterError, RateLimitedError) as exc:
            yield _sse("error", {"detail": str(exc)})
        finally:
            await close_django_connections()

    return StreamingResponse(event_source(), media_type="text/event-stream")
