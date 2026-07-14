"""
AI -> Core-facing interface — mirrors core/interface.py in the other
direction (API.md §12). This is the only seam Core's chat views cross to
reach chat orchestration: they pass ids in, get ChatEvents out, and never
import ai.chat_orchestrator, ai.model_router, or ai.tool_executor directly.

(Core's chat views *do* import ai.models.Conversation/Message directly for
plain CRUD — listing/reading conversations and messages is boring,
workspace-scoped, relationally-modeled reading with no business rule to
bypass, unlike sending a message or resuming after approval, both of which
carry real orchestration logic and stay behind this interface. Documented as
a deliberate, narrow deviation from ARCHITECTURE.md §3.1's "Core never
imports AI internals" ideal — see ARCHITECTURE.md §3.1's note.)
"""

from __future__ import annotations

from ai.tool_executor import execute_tool

from collections.abc import Iterator
from uuid import UUID

from ai.chat_orchestrator import ChatEvent
from ai.chat_orchestrator import regenerate_turn as _regenerate_turn
from ai.chat_orchestrator import resume_turn as _resume_turn
from ai.chat_orchestrator import start_turn as _start_turn
from ai.models import Conversation, Message

__all__ = [
    "ChatEvent",
    "ConversationNotFoundError",
    "MessageNotFoundError",
    "start_turn",
    "resume_turn",
    "regenerate_turn",
]


class ConversationNotFoundError(LookupError):
    """No Conversation with this id exists."""


class MessageNotFoundError(LookupError):
    """No Message with this id exists."""


def _get_conversation(conversation_id: UUID | str) -> Conversation:
    try:
        return Conversation.objects.get(id=conversation_id)
    except Conversation.DoesNotExist as exc:
        raise ConversationNotFoundError(f"No conversation {conversation_id}.") from exc


def _get_message(message_id: UUID | str) -> Message:
    try:
        return Message.objects.get(id=message_id)
    except Message.DoesNotExist as exc:
        raise MessageNotFoundError(f"No message {message_id}.") from exc


def start_turn(
    *,
    conversation_id: UUID | str,
    coworker_id: UUID | str,
    workspace_id: UUID | str,
    user_id: UUID | str,
    content: str,
) -> Iterator[ChatEvent]:
    conversation = _get_conversation(conversation_id)
    yield from _start_turn(
        conversation=conversation,
        coworker_id=coworker_id,
        workspace_id=workspace_id,
        user_id=user_id,
        content=content,
    )


def resume_turn(
    *, conversation_id: UUID | str, coworker_id: UUID | str, workspace_id: UUID | str
) -> Iterator[ChatEvent]:
    conversation = _get_conversation(conversation_id)
    yield from _resume_turn(
        conversation=conversation, coworker_id=coworker_id, workspace_id=workspace_id
    )


def regenerate_turn(
    *,
    conversation_id: UUID | str,
    coworker_id: UUID | str,
    workspace_id: UUID | str,
    target_message_id: UUID | str,
) -> Iterator[ChatEvent]:
    conversation = _get_conversation(conversation_id)
    target_message = _get_message(target_message_id)
    yield from _regenerate_turn(
        conversation=conversation,
        coworker_id=coworker_id,
        workspace_id=workspace_id,
        target_message=target_message,
    )
# Phase 2 workflow seam: Core owns durable Workflow records while AI owns
# concrete tool execution. Keeping this wrapper here preserves that boundary.
def execute_workflow_tool(tool_name: str, arguments: dict, *, workspace_id):
    return execute_tool(tool_name, arguments, workspace_id=workspace_id)
