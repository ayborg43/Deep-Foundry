"""
Tool execution — the concrete implementations behind the built-in
`core.models.Tool` rows seeded in core/migrations/0004_seed_builtin_tools.py
(web_search, read_file, write_file, execute_code), per SECURITY.md §5.

AI-owned per ARCHITECTURE.md §3.1 ("agent execution" is AI's domain).
Invoked only from ai.chat_orchestrator, only after
core.permissions.resolve_tool_permission has cleared the call outright, or a
human has approved it through the approval gate — this module does no
permission checking of its own and trusts its caller on that point.

Web search is bounded and provider-backed. Code is sent to the private sandbox
daemon, which creates one hardened, networkless container per approved call.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import urllib.error
import urllib.request
from uuid import UUID

from django.conf import settings
from django.core.mail import send_mail

from ai.sandbox import SandboxError, run_python
from ai.web_search import WebSearchError, search_web
from core.interface import (
    OrchestrationError,
    create_workspace_artifact,
    get_enabled_integration,
    get_workspace_overview,
    orchestrate_create_coworker,
    orchestrate_create_task,
    orchestrate_create_team,
    orchestrate_run_team,
    orchestrate_schedule_workflow,
)


class ToolExecutionError(Exception):
    """A tool-level failure (bad arguments, path traversal, missing file).
    Caught by the orchestrator and surfaced as a tool_call_result error
    event — never allowed to crash the chat turn."""


@dataclass(frozen=True)
class ToolResult:
    output: dict[str, Any]
    error: str | None = None


def _workspace_root(workspace_id: UUID | str) -> Path:
    root = Path(settings.WORKSPACE_FILES_ROOT) / str(workspace_id)
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _resolve_within_workspace(workspace_id: UUID | str, relative_path: str) -> Path:
    root = _workspace_root(workspace_id)
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ToolExecutionError(
            f"Path {relative_path!r} escapes the workspace's granted folder."
        )
    return candidate


def _web_search(arguments: dict[str, Any], *, workspace_id: UUID | str) -> ToolResult:
    query = arguments.get("query", "")
    try:
        results = search_web(query, max_results=arguments.get("max_results"))
    except WebSearchError as exc:
        return ToolResult(output={"results": []}, error=str(exc))
    return ToolResult(output={"results": results})


def _read_file(arguments: dict[str, Any], *, workspace_id: UUID | str) -> ToolResult:
    path = arguments.get("path")
    if not path:
        raise ToolExecutionError("read_file requires 'path'.")
    target = _resolve_within_workspace(workspace_id, path)
    if not target.is_file():
        raise ToolExecutionError(f"No such file: {path!r}.")
    return ToolResult(output={"content": target.read_text(errors="replace")})


def _write_file(arguments: dict[str, Any], *, workspace_id: UUID | str) -> ToolResult:
    path = arguments.get("path")
    content = arguments.get("content")
    if not path or content is None:
        raise ToolExecutionError("write_file requires 'path' and 'content'.")
    target = _resolve_within_workspace(workspace_id, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode()
    target.write_bytes(data)
    return ToolResult(output={"bytes_written": len(data)})


def _execute_code(arguments: dict[str, Any], *, workspace_id: UUID | str) -> ToolResult:
    language = str(arguments.get("language", "python")).lower()
    if language not in {"python", "py"}:
        return ToolResult(
            output={"stdout": "", "stderr": "", "exit_code": None},
            error=f"Unsupported sandbox language {language!r}; Phase 1 supports Python.",
        )
    try:
        result = run_python(str(arguments.get("code", "")))
    except SandboxError as exc:
        return ToolResult(
            output={"stdout": "", "stderr": "", "exit_code": None}, error=str(exc)
        )
    error = None
    if result.timed_out:
        error = f"Code execution exceeded {settings.SANDBOX_TIMEOUT_SECONDS} seconds."
    elif result.exit_code:
        error = f"Code exited with status {result.exit_code}."
    return ToolResult(
        output={
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "truncated": result.truncated,
        },
        error=error,
    )


def _integration_post(kind: str, arguments: dict[str, Any], *, workspace_id: UUID | str) -> ToolResult:
    integration = get_enabled_integration(workspace_id=workspace_id, kind=kind)
    if integration is None:
        raise ToolExecutionError(f"No enabled {kind} integration is configured.")
    config, secret = integration["config"], integration["secret"]
    endpoint = arguments.get("url") or config.get("endpoint_url")
    if not endpoint or not str(endpoint).startswith("https://"):
        raise ToolExecutionError(f"The {kind} integration requires an HTTPS endpoint_url.")
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(arguments.get("payload", arguments)).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read(2000).decode(errors="replace")
            return ToolResult(output={"status_code": response.status, "response": body})
    except urllib.error.HTTPError as exc:
        return ToolResult(output={"status_code": exc.code}, error=str(exc))
    except urllib.error.URLError as exc:
        return ToolResult(output={"status_code": None}, error=str(exc))


def _send_email(arguments: dict[str, Any], *, workspace_id: UUID | str) -> ToolResult:
    integration = get_enabled_integration(workspace_id=workspace_id, kind="email")
    if integration is None:
        raise ToolExecutionError("No enabled email integration is configured.")
    recipients = arguments.get("to") or []
    if isinstance(recipients, str): recipients = [recipients]
    if not recipients or not arguments.get("subject"):
        raise ToolExecutionError("send_email requires to, subject, and body.")
    count = send_mail(arguments["subject"], arguments.get("body", ""), integration["config"].get("from_email", settings.DEFAULT_FROM_EMAIL), recipients, fail_silently=False)
    return ToolResult(output={"sent": count})


def _post_tweet(arguments: dict[str, Any], *, workspace_id: UUID | str) -> ToolResult:
    """POST /2/tweets with the integration secret as the OAuth 2.0 user
    access token. Dedicated executor (vs _integration_post) because the X
    API has a fixed endpoint, an exact payload shape, and a 280-character
    limit worth rejecting before the call spends a human approval."""
    integration = get_enabled_integration(workspace_id=workspace_id, kind="twitter")
    if integration is None:
        raise ToolExecutionError("No enabled twitter integration is configured.")
    config, secret = integration["config"], integration["secret"]
    if not secret:
        raise ToolExecutionError(
            "The twitter integration requires an OAuth 2.0 user access token as its secret."
        )
    text = str(arguments.get("text", "")).strip()
    if not text:
        raise ToolExecutionError("post_tweet requires non-empty text.")
    if len(text) > 280:
        raise ToolExecutionError(f"post_tweet text is {len(text)} characters; the limit is 280.")
    endpoint = config.get("endpoint_url") or "https://api.x.com/2/tweets"
    if not str(endpoint).startswith("https://"):
        raise ToolExecutionError("The twitter integration requires an HTTPS endpoint_url.")
    payload: dict[str, Any] = {"text": text}
    if arguments.get("in_reply_to_tweet_id"):
        payload["reply"] = {"in_reply_to_tweet_id": str(arguments["in_reply_to_tweet_id"])}
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {secret}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read(2000).decode(errors="replace")
            try:
                tweet = json.loads(body).get("data", {})
            except (json.JSONDecodeError, AttributeError):
                tweet = {}
            return ToolResult(
                output={"status_code": response.status, "tweet_id": tweet.get("id"), "text": tweet.get("text")}
            )
    except urllib.error.HTTPError as exc:
        detail = exc.read(2000).decode(errors="replace")
        return ToolResult(output={"status_code": exc.code, "response": detail}, error=str(exc))
    except urllib.error.URLError as exc:
        return ToolResult(output={"status_code": None}, error=str(exc))


def _integration_executor(kind: str):
    return lambda arguments, *, workspace_id: _integration_post(kind, arguments, workspace_id=workspace_id)


def _artifact_executor(artifact_type: str):
    def execute(arguments: dict[str, Any], *, workspace_id: UUID | str) -> ToolResult:
        name = str(arguments.get("name") or arguments.get("title") or artifact_type.replace("_", " ").title())
        content = arguments.get("content") or {
            key: value for key, value in arguments.items() if key not in ("name", "title", "coworker_id")
        }
        if not isinstance(content, dict) or not content:
            raise ToolExecutionError(f"{artifact_type} requires structured content.")
        return ToolResult(output=create_workspace_artifact(
            workspace_id=workspace_id, artifact_type=artifact_type, name=name,
            content=content, coworker_id=arguments.get("coworker_id"),
        ))
    return execute


def _propose_capability(arguments: dict[str, Any], *, workspace_id: UUID | str) -> ToolResult:
    """Create a review request only; this executor can never grant capability."""
    from core.models import Coworker
    from core.v4_services import create_capability_proposal

    coworker = Coworker.objects.filter(
        id=arguments.get("coworker_id"), workspace_id=workspace_id
    ).first()
    if coworker is None:
        raise ToolExecutionError("propose_capability requires this coworker's valid coworker_id.")
    proposal = create_capability_proposal(
        coworker=coworker,
        target_type=str(arguments.get("target_type", "")),
        target_id=arguments.get("target_id"),
        rationale=str(arguments.get("rationale", "")),
    )
    return ToolResult(output={"proposal_id": str(proposal.id), "status": proposal.status})


# --- Workspace orchestration tools ------------------------------------------
# Thin wrappers over core.interface orchestration functions so a coworker in
# chat can report on and (approval-gated) reshape the workspace. Spec problems
# surface as ToolExecutionError text the model can read and correct.


def _orchestration_executor(fn, required: tuple[str, ...]):
    def execute(arguments: dict[str, Any], *, workspace_id: UUID | str) -> ToolResult:
        from rest_framework.exceptions import PermissionDenied, ValidationError

        kwargs = {key: arguments.get(key) for key in required}
        try:
            return ToolResult(output=fn(workspace_id=workspace_id, **kwargs))
        except (OrchestrationError, ValidationError, PermissionDenied) as exc:
            raise ToolExecutionError(str(exc)) from exc

    return execute


def _workspace_status(arguments: dict[str, Any], *, workspace_id: UUID | str) -> ToolResult:
    return ToolResult(output=get_workspace_overview(workspace_id=workspace_id))


_EXECUTORS = {
    "web_search": _web_search,
    "read_file": _read_file,
    "write_file": _write_file,
    "execute_code": _execute_code,
    "send_email": _send_email,
    "create_calendar_event": _integration_executor("calendar"),
    "send_slack_message": _integration_executor("slack"),
    "send_discord_message": _integration_executor("discord"),
    "create_github_issue": _integration_executor("github"),
    "post_tweet": _post_tweet,
    "send_webhook": _integration_executor("webhook"),
    "create_presentation": _artifact_executor("presentation"),
    "create_diagram": _artifact_executor("diagram"),
    "record_video_analysis": _artifact_executor("video_analysis"),
    "propose_capability": _propose_capability,
    "workspace_status": _workspace_status,
    "create_coworker": _orchestration_executor(
        orchestrate_create_coworker, ("name", "role_description", "tools")
    ),
    "create_agent_team": _orchestration_executor(
        orchestrate_create_team, ("name", "collaboration_pattern", "members")
    ),
    "run_agent_team": _orchestration_executor(orchestrate_run_team, ("team", "objective")),
    "create_task": _orchestration_executor(
        orchestrate_create_task, ("coworker", "title", "description")
    ),
    "schedule_workflow": _orchestration_executor(
        orchestrate_schedule_workflow, ("name", "schedule_cron", "steps")
    ),
}


def execute_tool(
    tool_name: str, arguments: dict[str, Any], *, workspace_id: UUID | str
) -> ToolResult:
    executor = _EXECUTORS.get(tool_name)
    if executor is None:
        raise ToolExecutionError(f"No executor registered for tool {tool_name!r}.")
    return executor(arguments, workspace_id=workspace_id)
