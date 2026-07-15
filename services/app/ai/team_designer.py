"""
AI-designed starter teams: ask the workspace's model to propose a team of
coworkers for a plain-language description of a company or project. Returns a
spec in exactly the shape core.starter_teams.provision_team consumes — this
module only *proposes*; creation happens after a human reviews the spec.
"""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from ai.model_router.factory import build_model_router
from ai.model_router.types import ChatMessage, ModelConfig
from core.models import AgentTeam, AgentTeamMember, Tool
from core.starter_teams import MAX_TEAM_SIZE


class TeamDesignError(Exception):
    """The model's proposal couldn't be parsed into a usable team spec."""


_SYSTEM_PROMPT = """You design small teams of AI coworkers for a work platform.
Given a description of a company or project, propose 2 to {max_size} coworkers.

Respond with ONLY a JSON object, no prose, in exactly this shape:
{{
  "team_name": "short team name",
  "collaboration_pattern": one of {patterns},
  "coworkers": [
    {{
      "name": "short coworker name",
      "team_role": one of {roles},
      "custom_role_label": "only when team_role is custom",
      "role_description": "2-4 sentences of system-prompt-style instructions, second person",
      "tools": subset of {tools}
    }}
  ]
}}

Rules:
- If collaboration_pattern is "manager_delegate", exactly one coworker has team_role "manager".
- Give each coworker only the tools its role actually needs.
- role_description must be concrete instructions, not a job ad."""


def _extract_json(text: str) -> dict[str, Any]:
    """Models often wrap JSON in ```fences``` or prefix a sentence; pull the
    first {...} object out rather than trusting the raw string."""
    candidate = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.DOTALL)
    if fenced:
        candidate = fenced.group(1)
    else:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            raise TeamDesignError("The model did not return a JSON team proposal.")
        candidate = candidate[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise TeamDesignError("The model returned malformed JSON.") from exc
    if not isinstance(parsed, dict):
        raise TeamDesignError("The model's proposal was not a JSON object.")
    return parsed


def _sanitize(parsed: dict[str, Any], tool_names: set[str]) -> dict[str, Any]:
    """Coerce the model's output into a spec provision_team will accept:
    clamp size, drop unknown tools, coerce roles, and repair the
    exactly-one-manager invariant instead of failing on it."""
    raw_members = parsed.get("coworkers")
    if not isinstance(raw_members, list) or not raw_members:
        raise TeamDesignError("The proposal contained no coworkers.")

    members: list[dict[str, Any]] = []
    for raw in raw_members[:MAX_TEAM_SIZE]:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "")).strip()
        role_description = str(raw.get("role_description", "")).strip()
        if not name or not role_description:
            continue
        team_role = str(raw.get("team_role", "")).strip().lower()
        custom_label = str(raw.get("custom_role_label", "")).strip()
        if team_role not in AgentTeamMember.Role.values:
            custom_label = custom_label or (team_role.replace("_", " ").title() if team_role else "")
            team_role = AgentTeamMember.Role.CUSTOM
        raw_tools = raw.get("tools") if isinstance(raw.get("tools"), list) else []
        members.append(
            {
                "name": name[:255],
                "team_role": team_role,
                "custom_role_label": custom_label[:100],
                "role_description": role_description,
                "tools": [str(t) for t in raw_tools if str(t) in tool_names],
            }
        )
    if not members:
        raise TeamDesignError("The proposal contained no usable coworkers.")

    pattern = str(parsed.get("collaboration_pattern", "")).strip().lower()
    if pattern not in AgentTeam.CollaborationPattern.values:
        pattern = AgentTeam.CollaborationPattern.SEQUENTIAL
    manager_count = sum(m["team_role"] == AgentTeamMember.Role.MANAGER for m in members)
    if pattern == AgentTeam.CollaborationPattern.MANAGER_DELEGATE and manager_count != 1:
        # Repair rather than reject: promote the first member, demote extras.
        if manager_count == 0:
            members[0]["team_role"] = AgentTeamMember.Role.MANAGER
        else:
            seen = False
            for member in members:
                if member["team_role"] == AgentTeamMember.Role.MANAGER:
                    if seen:
                        member["team_role"] = AgentTeamMember.Role.CUSTOM
                        member["custom_role_label"] = member["custom_role_label"] or "Lead"
                    seen = True

    return {
        "team_name": str(parsed.get("team_name", "")).strip()[:255] or "Proposed team",
        "collaboration_pattern": pattern,
        "coworkers": members,
    }


def design_team(*, workspace_id: UUID | str, description: str) -> dict[str, Any]:
    """One non-streaming model call → sanitized team spec. Raises
    CredentialNotFoundError (no provider key), AdapterError (API failure),
    or TeamDesignError (unusable output) — callers map these to HTTP."""
    tool_names = set(Tool.objects.values_list("name", flat=True))
    prompt = _SYSTEM_PROMPT.format(
        max_size=MAX_TEAM_SIZE,
        patterns=json.dumps(list(AgentTeam.CollaborationPattern.values)),
        roles=json.dumps(list(AgentTeamMember.Role.values)),
        tools=json.dumps(sorted(tool_names)),
    )
    router = build_model_router(workspace_id=workspace_id)
    response = router.generate(
        [
            ChatMessage(role="system", content=prompt),
            ChatMessage(role="user", content=description.strip()),
        ],
        [],
        ModelConfig(model_id="deepseek-v4-flash", temperature=0.4),
        fallback_model_id="deepseek-v4-pro",
    )
    return _sanitize(_extract_json(response.content), tool_names)
