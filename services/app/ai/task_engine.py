"""Durable background task orchestration for Milestone 6.

Every model/tool step is persisted in Task.execution_state before the worker
returns. A task paused for approval can therefore be resumed by any worker.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from ai.chat_orchestrator import summarize_approval
from ai.knowledge import search_coworker_knowledge
from ai.memory import search_memory, write_memory
from ai.model_router.factory import build_model_router
from ai.model_router.errors import AdapterError, CapabilityError, RateLimitedError
from ai.model_router.router import ModelRouter
from ai.model_router.types import ChatMessage, ModelConfig, ToolCall, ToolDefinition
from ai.response_style import RESPONSE_STYLE_PROMPT
from ai.tool_executor import ToolExecutionError, execute_tool
from core.interface import (
    claim_task_execution,
    create_approval_request,
    get_approval_request_for_task_call,
    get_attached_tools,
    get_coworker_config,
    get_provider_credential,
    notify_workspace,
    report_task_status,
    resolve_approval_policy,
    resolve_org_action_policy,
    write_audit_log,
)
from core.permissions import resolve_tool_permission

MAX_TASK_ITERATIONS = 10


def _serialize_message(message: ChatMessage) -> dict[str, Any]:
    return {
        "role": message.role,
        "content": message.content,
        "tool_call_id": message.tool_call_id,
        "tool_calls": [
            {"id": call.id, "name": call.name, "arguments": call.arguments}
            for call in message.tool_calls or []
        ],
    }


def _deserialize_message(raw: dict[str, Any]) -> ChatMessage:
    return ChatMessage(
        role=raw["role"],
        content=raw.get("content", ""),
        tool_call_id=raw.get("tool_call_id"),
        tool_calls=[ToolCall(**call) for call in raw.get("tool_calls") or []] or None,
    )


def _initial_messages(task, role_description: str) -> list[ChatMessage]:
    context: list[str] = []
    memories = search_memory(
        workspace_id=task.workspace_id,
        scope="coworker",
        scope_id=task.coworker_id,
        query=task.description,
        limit=4,
    )
    chunks = search_coworker_knowledge(
        coworker_id=task.coworker_id, query=task.description, limit=4
    )
    if memories:
        context.append("Memory:\n" + "\n".join(f"- {entry.content}" for entry in memories))
    if chunks:
        context.append(
            "Knowledge:\n"
            + "\n".join(f"- [{chunk.document.source_uri}] {chunk.content}" for chunk in chunks)
        )
    system = f"{role_description}\n\n{RESPONSE_STYLE_PROMPT}" + (
        "\n\nUse this retrieved context when relevant:\n" + "\n\n".join(context)
        if context
        else ""
    )
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(
            role="user",
            content=f"Complete this background task.\nTitle: {task.title}\nDescription: {task.description}",
        ),
    ]


def _notify(task, notification_type: str, **extra: Any) -> None:
    notify_workspace(
        workspace_id=task.workspace_id,
        notification_type=notification_type,
        payload={
            "task_id": str(task.id),
            "coworker_id": str(task.coworker_id),
            "title": task.title,
            **extra,
        },
    )


def execute_background_task(task_id: UUID | str) -> None:
    task = claim_task_execution(task_id)
    if task is None:
        return
    try:
        config = get_coworker_config(task.coworker_id)
        tools = get_attached_tools(task.coworker_id)
        tools_by_name = {tool.name: tool for tool in tools}
        definitions = [
            ToolDefinition(name=tool.name, description=tool.description, parameters=tool.input_schema)
            for tool in tools
        ]
        router = build_model_router(
            workspace_id=task.workspace_id,
            coworker_id=task.coworker_id,
            model_binding=config.model_binding,
        )
        messages = (
            [_deserialize_message(raw) for raw in task.execution_state.get("messages", [])]
            if task.execution_state.get("messages")
            else _initial_messages(task, config.role_description)
        )

        for _ in range(MAX_TASK_ITERATIONS):
            unresolved = next(
                (
                    message
                    for message in reversed(messages)
                    if message.role == "assistant"
                    and message.tool_calls
                    and any(
                        not any(
                            reply.role == "tool" and reply.tool_call_id == call.id
                            for reply in messages
                        )
                        for call in message.tool_calls
                    )
                ),
                None,
            )
            if unresolved is not None:
                for call in unresolved.tool_calls or []:
                    if any(
                        reply.role == "tool" and reply.tool_call_id == call.id for reply in messages
                    ):
                        continue
                    tool = tools_by_name.get(call.name)
                    if tool is None:
                        messages.append(
                            ChatMessage(
                                role="tool",
                                tool_call_id=call.id,
                                content=json.dumps({"error": f"Tool {call.name!r} is not attached."}),
                            )
                        )
                        continue
                    approval = get_approval_request_for_task_call(task.id, call.id)
                    if approval and approval.status == "pending":
                        report_task_status(
                            task.id,
                            "needs_approval",
                            execution_state={**task.execution_state, "messages": [_serialize_message(m) for m in messages]},
                        )
                        return
                    if approval and approval.status in ("denied", "expired"):
                        report_task_status(
                            task.id,
                            "blocked",
                            execution_state={**task.execution_state, "messages": [_serialize_message(m) for m in messages]},
                            error_message="A required action was denied.",
                        )
                        _notify(task, "task_completed", status="blocked")
                        return
                    org_decision = resolve_org_action_policy(
                        workspace_id=task.workspace_id, resource_type="tool", action="execute",
                        context={"tool_name": tool.name, "risk": tool.risk_classification},
                    )
                    if org_decision == "deny":
                        report_task_status(task.id, "blocked", error_message="Organization policy denied a required tool action.")
                        _notify(task, "task_completed", status="blocked")
                        return
                    permission_decision = resolve_tool_permission(
                        tool.risk_classification, config.permission_profile, config.org_policy_floor
                    )
                    if org_decision == "require_approval":
                        permission_decision = "approval"
                    elif permission_decision == "approval" and approval is None:
                        # Standing "always allow" consent — same guardrails
                        # as the chat orchestrator: never overrides an org
                        # floor or org action policy.
                        floor_forces = (config.org_policy_floor or {}).get(
                            tool.risk_classification, "auto"
                        ) != "auto"
                        if not floor_forces:
                            policy_id = resolve_approval_policy(
                                workspace_id=task.workspace_id,
                                coworker_id=task.coworker_id,
                                tool_id=tool.id,
                                arguments=call.arguments,
                            )
                            if policy_id is not None:
                                permission_decision = "auto"
                                write_audit_log(
                                    actor_type="coworker", actor_id=task.coworker_id,
                                    action="tool.policy_auto_approved", resource_type="tool",
                                    resource_id=tool.id, workspace_id=task.workspace_id,
                                    metadata={
                                        "tool_call_id": call.id,
                                        "approval_policy_id": str(policy_id),
                                    },
                                )
                    if approval is None and permission_decision == "approval":
                        summary, rationale = summarize_approval(
                            router,
                            config.model_binding.get("primary", "deepseek-v4-flash"),
                            call.name,
                            call.arguments,
                            unresolved.content,
                        )
                        approval = create_approval_request(
                            coworker_id=task.coworker_id,
                            tool_id=tool.id,
                            task_id=task.id,
                            requested_action={
                                "tool_call_id": call.id,
                                "name": call.name,
                                "arguments": call.arguments,
                            },
                            summary=summary,
                            rationale=rationale,
                        )
                        state = {**task.execution_state, "messages": [_serialize_message(m) for m in messages]}
                        report_task_status(task.id, "needs_approval", execution_state=state)
                        write_audit_log(
                            actor_type="coworker",
                            actor_id=task.coworker_id,
                            action="task.approval_requested",
                            resource_type="task",
                            resource_id=task.id,
                            workspace_id=task.workspace_id,
                            metadata={"approval_request_id": str(approval.id), "tool": call.name},
                        )
                        _notify(
                            task,
                            "approval_requested",
                            approval_request_id=str(approval.id),
                            tool_name=call.name,
                            arguments=call.arguments,
                        )
                        return
                    try:
                        executed = execute_tool(call.name, call.arguments, workspace_id=task.workspace_id)
                        output = dict(executed.output)
                        if executed.error:
                            output["error"] = executed.error
                    except ToolExecutionError as exc:
                        output = {"error": str(exc)}
                    messages.append(
                        ChatMessage(role="tool", tool_call_id=call.id, content=json.dumps(output))
                    )
                    write_audit_log(
                        actor_type="coworker",
                        actor_id=task.coworker_id,
                        action="task.tool_executed",
                        resource_type="task",
                        resource_id=task.id,
                        workspace_id=task.workspace_id,
                        metadata={"tool": call.name, "arguments": call.arguments, "result": output},
                    )
                report_task_status(
                    task.id,
                    "in_progress",
                    execution_state={**task.execution_state, "messages": [_serialize_message(m) for m in messages]},
                )
                continue

            binding = config.model_binding
            response = router.generate(
                messages,
                definitions,
                ModelConfig(model_id=binding.get("primary", "deepseek-v4-flash")),
                fallback_model_id=(binding.get("fallback") or [None])[0],
            )
            messages.append(
                ChatMessage(role="assistant", content=response.content, tool_calls=response.tool_calls or None)
            )
            state = {**task.execution_state, "messages": [_serialize_message(message) for message in messages]}
            if response.tool_calls:
                report_task_status(task.id, "in_progress", execution_state=state)
                continue
            report_task_status(task.id, "completed", execution_state=state, result=response.content)
            write_memory(
                workspace_id=task.workspace_id,
                scope="coworker",
                scope_id=task.coworker_id,
                content=f"Completed task '{task.title}': {response.content[:1600]}",
                source_type="task_result",
                source_ref_id=task.id,
                is_long_term=True,
            )
            write_audit_log(
                actor_type="coworker",
                actor_id=task.coworker_id,
                action="task.completed",
                resource_type="task",
                resource_id=task.id,
                workspace_id=task.workspace_id,
            )
            _notify(task, "task_completed", status="completed")
            return
        raise RuntimeError("Task exceeded the maximum model/tool iterations.")
    except Exception as exc:
        report_task_status(task.id, "failed", error_message=str(exc)[:2000])
        write_audit_log(
            actor_type="system",
            actor_id=None,
            action="task.failed",
            resource_type="task",
            resource_id=task.id,
            workspace_id=task.workspace_id,
            metadata={"error": str(exc)[:500]},
        )
        _notify(task, "task_completed", status="failed", error=str(exc)[:500])
