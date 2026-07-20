"""
Chat orchestration — the send-message -> stream -> (maybe pause for
approval) -> tool execution -> follow-up-call loop, per
IMPLEMENTATION_PLAN.md Milestone 4 and SECURITY.md §4.

AI-owned per ARCHITECTURE.md §3.1 ("agent execution" is AI's domain). The
only way Core reaches this logic is through `ai.interface` (mirroring the
seam `core.interface` exposes in the other direction) — this module is not
imported directly from Core.

State machine, in one sentence: every entry point (a fresh user message, or
resuming after an approval decision) funnels into `_continue_turn`, which
re-derives "what's left to do" entirely from stored rows — there is no
in-memory turn state — so a resume is not a special case, it's just another
call that finds different data already in Postgres.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.db import transaction

from ai.model_router.factory import build_model_router
from ai.model_router.errors import AdapterError, CapabilityError, RateLimitedError
from ai.model_router.router import ModelRouter
from ai.model_router.types import ChatMessage, ModelConfig, ToolCall, ToolDefinition
from ai.knowledge import search_coworker_knowledge
from ai.memory import remember_conversation_turn, search_memory
from ai.models import Conversation, MemoryEntry, Message
from ai.response_style import RESPONSE_STYLE_PROMPT
from ai.tool_executor import ToolExecutionError, execute_tool
from core.interface import (
    CoworkerNotFoundError,
    CredentialNotFoundError,
    ResolvedCoworkerConfig,
    ToolInfo,
    create_approval_request,
    get_approval_request_for_tool_call,
    get_attached_tools,
    get_coworker_config,
    get_provider_credential,
    resolve_approval_policy,
    resolve_org_action_policy,
    set_approval_request_summary,
    write_audit_log,
)
from core.permissions import resolve_tool_permission

logger = logging.getLogger(__name__)

# Bounds one invocation's model-call <-> tool-call cycles. Each call to
# start_turn/resume_turn gets its own fresh budget — this guards against a
# single request looping forever, not against a coworker calling tools
# across many separate turns.
MAX_TOOL_ITERATIONS = 5

_APPROVAL_SUMMARY_PROMPT = (
    "You summarize a pending tool action for a human approval queue. Reply with "
    "one short imperative headline (under 100 characters) stating the concrete "
    "action and its key numbers, e.g. 'Refund $214.00 across 3 Stripe charges'. "
    "No quotes, no trailing period, nothing else."
)


def summarize_approval(
    router: ModelRouter,
    model_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    assistant_content: str,
) -> tuple[str, str]:
    """Best-effort (summary, rationale) for an approval request. The
    rationale is the coworker's own words from the message that requested
    the call; the summary is one extra non-streaming model call. Any
    failure degrades to blank — approval surfaces always fall back to
    tool_name + requested_action, so nothing here may ever raise."""
    rationale = " ".join((assistant_content or "").split())
    if len(rationale) > 280:
        rationale = rationale[:277] + "..."
    try:
        response = router.generate(
            [
                ChatMessage(role="system", content=_APPROVAL_SUMMARY_PROMPT),
                ChatMessage(
                    role="user",
                    content=json.dumps({"tool": tool_name, "arguments": arguments}),
                ),
            ],
            [],
            ModelConfig(model_id=model_id, temperature=0.0, max_tokens=60),
        )
        summary = " ".join((response.content or "").split()).strip('"')
        if len(summary) > 140:
            summary = summary[:137] + "..."
    except Exception:  # noqa: BLE001 — summary is decorative, never fatal
        summary = ""
    return summary, rationale


@dataclass(frozen=True)
class ChatEvent:
    # token | tool_call_started | tool_call_result | approval_required | message_complete | error
    event: str
    data: dict[str, Any]


def start_turn(
    *,
    conversation: Conversation,
    coworker_id: UUID | str,
    workspace_id: UUID | str,
    user_id: UUID | str,
    content: str,
) -> Iterator[ChatEvent]:
    Message.objects.create(
        conversation=conversation,
        sender_type=Message.SenderType.USER,
        sender_id=user_id,
        content=content,
        status=Message.Status.COMPLETE,
    )
    if not conversation.title:
        # Untitled conversations (e.g. started from a coworker page) take
        # their title from the first user message, so lists never show
        # "Untitled conversation".
        condensed = " ".join(content.split())
        conversation.title = condensed if len(condensed) <= 80 else f"{condensed[:77]}..."
        conversation.save(update_fields=["title"])
    yield from _continue_turn(
        conversation=conversation, coworker_id=coworker_id, workspace_id=workspace_id
    )


def resume_turn(
    *, conversation: Conversation, coworker_id: UUID | str, workspace_id: UUID | str
) -> Iterator[ChatEvent]:
    """Called after core.interface.decide_approval_request has already
    flipped an approval_requests row — re-enters the same loop, which
    discovers the decision from the database like anything else here."""
    yield from _continue_turn(
        conversation=conversation, coworker_id=coworker_id, workspace_id=workspace_id
    )


def regenerate_turn(
    *,
    conversation: Conversation,
    coworker_id: UUID | str,
    workspace_id: UUID | str,
    target_message: Message,
) -> Iterator[ChatEvent]:
    """Re-runs the model against the history up to (not including)
    `target_message`, producing a new sibling response linked to it via
    `parent_message` — the original and anything chronologically after it
    are left untouched (DATABASE.md §3.3: parent_message_id is "for
    branching/regeneration", not deletion)."""
    exclude_ids = set(
        Message.objects.filter(
            conversation=conversation, created_at__gte=target_message.created_at
        ).values_list("id", flat=True)
    )
    yield from _continue_turn(
        conversation=conversation,
        coworker_id=coworker_id,
        workspace_id=workspace_id,
        exclude_message_ids=exclude_ids,
        link_new_message_to=target_message,
    )


def _continue_turn(
    *,
    conversation: Conversation,
    coworker_id: UUID | str,
    workspace_id: UUID | str,
    exclude_message_ids: frozenset = frozenset(),
    link_new_message_to: Message | None = None,
) -> Iterator[ChatEvent]:
    try:
        coworker_config = get_coworker_config(coworker_id)
    except CoworkerNotFoundError as exc:
        yield ChatEvent("error", {"detail": str(exc)})
        return

    try:
        router = build_model_router(
            workspace_id=workspace_id,
            coworker_id=coworker_id,
            model_binding=coworker_config.model_binding,
        )
    except (CredentialNotFoundError, ValueError) as exc:
        yield ChatEvent("error", {"detail": str(exc)})
        return

    attached_tools = get_attached_tools(coworker_id)
    tools_by_name = {t.name: t for t in attached_tools}
    tool_definitions = [
        ToolDefinition(name=t.name, description=t.description, parameters=t.input_schema)
        for t in attached_tools
    ]

    latest_user = (
        conversation.messages.filter(sender_type=Message.SenderType.USER)
        .exclude(id__in=exclude_message_ids)
        .order_by("-created_at")
        .first()
    )
    context_messages: list[ChatMessage] = []
    if latest_user is not None:
        memories = search_memory(
            workspace_id=workspace_id, scope="coworker", scope_id=coworker_id,
            query=latest_user.content, limit=4,
        )
        chunks = search_coworker_knowledge(
            coworker_id=coworker_id, query=latest_user.content, limit=4
        )
        if memories or chunks:
            sections = [
                "Use the following retrieved context when relevant. Do not invent facts "
                "outside it; identify document sources by name when using knowledge."
            ]
            if memories:
                sections.append("Memory:\n" + "\n".join(f"- {m.content}" for m in memories))
            if chunks:
                sections.append(
                    "Knowledge:\n" + "\n".join(
                        f"- [{c.document.source_uri}] {c.content}" for c in chunks
                    )
                )
            context_messages.append(ChatMessage(role="system", content="\n\n".join(sections)))

    for _ in range(MAX_TOOL_ITERATIONS):
        unresolved = _find_unresolved_tool_message(conversation, exclude_message_ids)
        if unresolved is not None:
            yield from _advance_message_tool_calls(
                conversation=conversation,
                assistant_message=unresolved,
                tools_by_name=tools_by_name,
                coworker_config=coworker_config,
                workspace_id=workspace_id,
                coworker_id=coworker_id,
                router=router,
            )
            if _has_unresolved_tool_calls(unresolved):
                return  # still blocked on at least one pending approval
            unresolved.status = Message.Status.COMPLETE
            unresolved.save(update_fields=["status"])
            continue  # call the model again with the new tool result(s) in history

        messages = _build_history(conversation, coworker_config, exclude_message_ids)
        messages[1:1] = context_messages
        model_config = ModelConfig(
            model_id=coworker_config.model_binding.get("primary", "deepseek-v4-flash"),
            stream=True,
        )

        content_parts: list[str] = []
        final_tool_calls: list[ToolCall] | None = None
        try:
            for chunk in router.generate_stream(messages, tool_definitions, model_config):
                if chunk.delta:
                    content_parts.append(chunk.delta)
                    yield ChatEvent("token", {"delta": chunk.delta})
                if chunk.tool_calls:
                    final_tool_calls = chunk.tool_calls
        except (AdapterError, RateLimitedError, CapabilityError) as exc:
            yield ChatEvent("error", {"detail": str(exc)})
            return

        assistant_content = "".join(content_parts)

        if not final_tool_calls:
            completed_message = Message.objects.create(
                conversation=conversation,
                sender_type=Message.SenderType.COWORKER,
                sender_id=coworker_id,
                content=assistant_content,
                status=Message.Status.COMPLETE,
                parent_message=link_new_message_to,
            )
            from research.citations import attach_message_citations

            # Citation enrichment must never turn a successfully generated
            # answer into a failed chat turn. The source panel is additive;
            # malformed legacy tool output is safely ignored.
            try:
                citations = attach_message_citations(
                    completed_message,
                    query=latest_user.content if latest_user is not None else "",
                )
            except Exception:
                logger.exception(
                    "Unable to attach citations to message %s", completed_message.id
                )
                citations = []
            if latest_user is not None and not MemoryEntry.objects.filter(
                workspace_id=workspace_id,
                scope=MemoryEntry.Scope.COWORKER,
                scope_id=coworker_id,
                source_type=MemoryEntry.SourceType.CONVERSATION,
                source_ref_id=latest_user.id,
            ).exists():
                remember_conversation_turn(
                    workspace_id=workspace_id, coworker_id=coworker_id,
                    conversation_id=latest_user.id, user_content=latest_user.content,
                    assistant_content=assistant_content,
                )
            yield ChatEvent(
                "message_complete",
                {
                    "content": assistant_content,
                    "message_id": str(completed_message.id),
                    "citation_count": len(citations),
                },
            )
            return

        assistant_message = Message.objects.create(
            conversation=conversation,
            sender_type=Message.SenderType.COWORKER,
            sender_id=coworker_id,
            content=assistant_content,
            tool_calls=[
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in final_tool_calls
            ],
            status=Message.Status.STREAMING,
            parent_message=link_new_message_to,
        )
        link_new_message_to = None  # only the first new message in this call links back
        yield from _advance_message_tool_calls(
            conversation=conversation,
            assistant_message=assistant_message,
            tools_by_name=tools_by_name,
            coworker_config=coworker_config,
            workspace_id=workspace_id,
            coworker_id=coworker_id,
            router=router,
        )
        if _has_unresolved_tool_calls(assistant_message):
            return  # blocked on approval
        assistant_message.status = Message.Status.COMPLETE
        assistant_message.save(update_fields=["status"])
        # loop again: history now includes the tool result(s)

    yield ChatEvent(
        "error", {"detail": "Tool-call loop exceeded the maximum number of iterations."}
    )


# -- tool-call resolution ---------------------------------------------------


def _started_event(tool_name: str, arguments: dict[str, Any], message_id: UUID | str) -> ChatEvent:
    return ChatEvent(
        "tool_call_started",
        {"tool_name": tool_name, "arguments": arguments, "message_id": str(message_id)},
    )


def _result_event(tool_name: str, result: dict[str, Any], message_id: UUID | str) -> ChatEvent:
    return ChatEvent(
        "tool_call_result",
        {"tool_name": tool_name, "result": result, "message_id": str(message_id)},
    )


def _find_unresolved_tool_message(
    conversation: Conversation, exclude_message_ids: frozenset = frozenset()
) -> Message | None:
    candidate = (
        Message.objects.filter(
            conversation=conversation,
            sender_type=Message.SenderType.COWORKER,
            tool_calls__isnull=False,
        )
        .exclude(id__in=exclude_message_ids)
        .order_by("-created_at")
        .first()
    )
    if candidate is not None and _has_unresolved_tool_calls(candidate):
        return candidate
    return None


def _has_unresolved_tool_calls(message: Message) -> bool:
    for raw in message.tool_calls or []:
        if not Message.objects.filter(parent_message=message, tool_call_id=raw["id"]).exists():
            return True
    return False


def _advance_message_tool_calls(
    *,
    conversation: Conversation,
    assistant_message: Message,
    tools_by_name: dict[str, ToolInfo],
    coworker_config: ResolvedCoworkerConfig,
    workspace_id: UUID | str,
    coworker_id: UUID | str,
    router: ModelRouter | None = None,
) -> Iterator[ChatEvent]:
    """Walks the assistant message's stored tool_calls in order, resolving
    whichever prefix is resolvable right now. Idempotent by construction: a
    call already answered by a stored result Message is skipped, a call
    whose approval_requests row already carries a decision is executed or
    recorded-denied, and the first call with neither is either auto-executed
    or turned into a fresh approval request — at which point this stops."""
    for raw in assistant_message.tool_calls or []:
        tool_call_id = raw["id"]
        outcome = _resolve_one_tool_call(
            conversation=conversation,
            assistant_message=assistant_message,
            tool_call_id=tool_call_id,
            tool_name=raw["name"],
            arguments=raw["arguments"],
            tools_by_name=tools_by_name,
            coworker_config=coworker_config,
            workspace_id=workspace_id,
            coworker_id=coworker_id,
        )
        if outcome is None:
            continue  # already resolved by this call or a concurrent one
        events, stop = outcome
        # A freshly created approval request gets its human-readable
        # headline here, after _resolve_one_tool_call's transaction has
        # committed — the summary is a model call and must never run while
        # the assistant_message row lock is held.
        approval_event = next((e for e in events if e.event == "approval_required"), None)
        if approval_event is not None and router is not None:
            summary, rationale = summarize_approval(
                router,
                coworker_config.model_binding.get("primary", "deepseek-v4-flash"),
                raw["name"],
                raw["arguments"],
                assistant_message.content,
            )
            if summary or rationale:
                set_approval_request_summary(
                    approval_event.data["approval_request_id"],
                    summary=summary,
                    rationale=rationale,
                )
                approval_event.data["summary"] = summary
                approval_event.data["rationale"] = rationale
        yield from events
        if stop:
            return


def _resolve_one_tool_call(
    *,
    conversation: Conversation,
    assistant_message: Message,
    tool_call_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    tools_by_name: dict[str, ToolInfo],
    coworker_config: ResolvedCoworkerConfig,
    workspace_id: UUID | str,
    coworker_id: UUID | str,
) -> tuple[list[ChatEvent], bool] | None:
    """Resolves exactly one tool call, inside a transaction holding a lock
    on `assistant_message` for the duration. This closes a check-then-act
    race: two concurrent resume_turn calls (a double-click, a client retry)
    could otherwise both pass the "not yet resolved" check before either
    stored a result, and both execute the tool for one approval. Locking
    the assistant_message row serializes concurrent attempts to resolve its
    tool calls — the loser re-checks after acquiring the lock and finds it
    already resolved. Events are collected and returned (not yielded)
    precisely so nothing yields — and thus nothing can pause this generator
    mid-transaction — while the lock is held.

    Returns None if already resolved, else (events, stop) where `stop`
    means the caller should return after yielding `events`.
    """
    with transaction.atomic():
        Message.objects.select_for_update().get(id=assistant_message.id)
        if Message.objects.filter(
            parent_message=assistant_message, tool_call_id=tool_call_id
        ).exists():
            return None

        existing = get_approval_request_for_tool_call(assistant_message.id, tool_call_id)
        if existing is not None:
            if existing.status == "pending":
                return [], True  # still waiting on a human
            if existing.status == "approved":
                events = [_started_event(tool_name, arguments, assistant_message.id)]
                result = _execute_and_log(
                    tool_name, arguments, tool_id=existing.tool_id,
                    workspace_id=workspace_id, coworker_id=coworker_id,
                )
                _store_tool_result(conversation, assistant_message, tool_call_id, result)
                events.append(_result_event(tool_name, result, assistant_message.id))
            else:  # denied or expired
                result = {"denied": True, "message": "This action was denied."}
                _store_tool_result(conversation, assistant_message, tool_call_id, result)
                events = [_result_event(tool_name, result, assistant_message.id)]
            return events, False

        tool_info = tools_by_name.get(tool_name)
        if tool_info is None:
            # The model asked for a tool that isn't attached — record a
            # synthetic error result rather than crash the whole turn over
            # a hallucinated tool name.
            result = {"error": f"Tool {tool_name!r} is not attached to this coworker."}
            _store_tool_result(conversation, assistant_message, tool_call_id, result)
            return [_result_event(tool_name, result, assistant_message.id)], False

        org_decision = resolve_org_action_policy(
            workspace_id=workspace_id, resource_type="tool", action="execute",
            context={"tool_name": tool_name, "risk": tool_info.risk_classification},
        )
        if org_decision == "deny":
            result = {"denied": True, "message": "Organization policy denied this action."}
            _store_tool_result(conversation, assistant_message, tool_call_id, result)
            write_audit_log(actor_type="coworker", actor_id=coworker_id, action="tool.policy_denied", resource_type="tool", resource_id=tool_info.id, workspace_id=workspace_id, metadata={"tool_name": tool_name})
            return [_result_event(tool_name, result, assistant_message.id)], False
        decision = resolve_tool_permission(
            tool_info.risk_classification,
            coworker_config.permission_profile,
            coworker_config.org_policy_floor,
        )
        if org_decision == "require_approval":
            decision = "approval"
        elif decision == "approval":
            # A member-created "always allow" policy is standing human
            # consent — equivalent to clicking Approve in advance. It may
            # override the default gate, but never org governance: this
            # branch is unreachable when the org action policy forced
            # approval, and the floor check below keeps floor-forced
            # approvals gated too.
            floor_forces = (coworker_config.org_policy_floor or {}).get(
                tool_info.risk_classification, "auto"
            ) != "auto"
            if not floor_forces:
                policy_id = resolve_approval_policy(
                    workspace_id=workspace_id,
                    coworker_id=coworker_id,
                    tool_id=tool_info.id,
                    arguments=arguments,
                )
                if policy_id is not None:
                    decision = "auto"
                    write_audit_log(
                        actor_type="coworker", actor_id=coworker_id,
                        action="tool.policy_auto_approved", resource_type="tool",
                        resource_id=tool_info.id, workspace_id=workspace_id,
                        metadata={
                            "tool_call_id": tool_call_id,
                            "approval_policy_id": str(policy_id),
                        },
                    )
        if decision == "approval":
            requested_action = {
                "tool_call_id": tool_call_id, "name": tool_name, "arguments": arguments
            }
            approval = create_approval_request(
                coworker_id=coworker_id,
                tool_id=tool_info.id,
                requested_action=requested_action,
                conversation_id=conversation.id,
                message_id=assistant_message.id,
            )
            write_audit_log(
                actor_type="coworker", actor_id=coworker_id, action="tool.approval_requested",
                resource_type="tool", resource_id=tool_info.id, workspace_id=workspace_id,
                metadata={"tool_call_id": tool_call_id, "approval_request_id": str(approval.id)},
            )
            assistant_message.status = Message.Status.NEEDS_APPROVAL
            assistant_message.save(update_fields=["status"])
            event = ChatEvent(
                "approval_required",
                {
                    "approval_request_id": str(approval.id),
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "message_id": str(assistant_message.id),
                    # Filled in by _advance_message_tool_calls after this
                    # transaction commits (summary generation is a model call).
                    "summary": "",
                    "rationale": "",
                },
            )
            return [event], True  # stop; wait for a decision

        events = [_started_event(tool_name, arguments, assistant_message.id)]
        result = _execute_and_log(
            tool_name, arguments,
            tool_id=tool_info.id, workspace_id=workspace_id, coworker_id=coworker_id,
        )
        _store_tool_result(conversation, assistant_message, tool_call_id, result)
        events.append(_result_event(tool_name, result, assistant_message.id))
        return events, False


def _execute_and_log(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    tool_id: UUID | str,
    workspace_id: UUID | str,
    coworker_id: UUID | str,
) -> dict[str, Any]:
    try:
        tool_result = execute_tool(tool_name, arguments, workspace_id=workspace_id)
        output = dict(tool_result.output)
        if tool_result.error:
            output["error"] = tool_result.error
    except ToolExecutionError as exc:
        output = {"error": str(exc)}
    write_audit_log(
        actor_type="coworker", actor_id=coworker_id, action="tool.executed",
        resource_type="tool", resource_id=tool_id, workspace_id=workspace_id,
        metadata={"tool_name": tool_name, "arguments": arguments, "result": output},
    )
    return output


def _store_tool_result(
    conversation: Conversation,
    assistant_message: Message,
    tool_call_id: str,
    result: dict[str, Any],
) -> None:
    Message.objects.create(
        conversation=conversation,
        sender_type=Message.SenderType.SYSTEM,
        content=json.dumps(result),
        tool_call_id=tool_call_id,
        parent_message=assistant_message,
        status=Message.Status.COMPLETE,
    )


def _build_history(
    conversation: Conversation,
    coworker_config: ResolvedCoworkerConfig,
    exclude_message_ids: frozenset = frozenset(),
) -> list[ChatMessage]:
    history = [
        ChatMessage(
            role="system",
            content=f"{coworker_config.role_description}\n\n{RESPONSE_STYLE_PROMPT}",
        )
    ]
    query = conversation.messages.order_by("created_at")
    if exclude_message_ids:
        query = query.exclude(id__in=exclude_message_ids)
    for message in query:
        if message.sender_type == Message.SenderType.USER:
            history.append(ChatMessage(role="user", content=message.content))
        elif message.sender_type == Message.SenderType.COWORKER:
            tool_calls = (
                [
                    ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
                    for tc in message.tool_calls
                ]
                if message.tool_calls
                else None
            )
            history.append(
                ChatMessage(role="assistant", content=message.content, tool_calls=tool_calls)
            )
        elif message.sender_type == Message.SenderType.SYSTEM and message.tool_call_id:
            history.append(
                ChatMessage(role="tool", content=message.content, tool_call_id=message.tool_call_id)
            )
    return history
