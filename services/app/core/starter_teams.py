"""
Starter-team provisioning: turn a team spec — from a curated template or an
AI-designed proposal (ai.team_designer) — into real coworkers, tool
attachments, and (when the spec has 2+ members) an agent team.

Both entry points converge on provision_team() so template teams and
AI-generated teams are created by exactly the same code path.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from rest_framework.exceptions import ValidationError

from core.coworkers import create_coworker
from core.models import AgentTeam, AgentTeamMember, Coworker, Tool, User, Workspace
from core.provisioning import DEFAULT_MODEL_BINDING
from core.v2_services import create_agent_team

# The largest team either path may create in one call — keeps a runaway spec
# (or prompt-injected model output) from flooding a workspace.
MAX_TEAM_SIZE = 6

# Attached automatically to every provisioned manager (and to a solo
# coworker): lets the user run the workspace from chat — see what teams are
# doing, start runs, hire coworkers, assign tasks, schedule workflows. The
# mutating ones are risk-classified sensitive, so they stay approval-gated.
ORCHESTRATION_TOOLS = (
    "workspace_status", "create_coworker", "create_agent_team",
    "run_agent_team", "create_task", "schedule_workflow",
)

# Curated blueprints. Tools must be names seeded in the platform Tool catalog;
# unknown names are skipped at attach time rather than failing the provision.
TEMPLATES: dict[str, dict[str, Any]] = {
    "software": {
        "label": "Software team",
        "description": "Plan, build, review, and test software changes.",
        "team_name": "Software team",
        "collaboration_pattern": AgentTeam.CollaborationPattern.MANAGER_DELEGATE,
        "coworkers": [
            {
                "name": "Tech Lead",
                "team_role": AgentTeamMember.Role.MANAGER,
                "tools": ["web_search", "read_webpage", "read_file", "write_file"],
                "role_description": (
                    "You are the technical lead. Break objectives into small, "
                    "verifiable engineering tasks, delegate them, and integrate the "
                    "results into a coherent deliverable. Flag risks and open "
                    "questions early instead of guessing."
                ),
            },
            {
                "name": "Developer",
                "team_role": AgentTeamMember.Role.DEVELOPER,
                "tools": ["web_search", "read_webpage", "read_file", "write_file", "execute_code"],
                "role_description": (
                    "You are a pragmatic software developer. Implement exactly what "
                    "the task asks, prefer the simplest working solution, run code "
                    "to check your work, and report what you verified."
                ),
            },
            {
                "name": "Code Reviewer",
                "team_role": AgentTeamMember.Role.REVIEWER,
                "tools": ["read_file", "web_search", "read_webpage"],
                "role_description": (
                    "You review work for correctness first, then clarity. Point at "
                    "specific lines, explain the failure case each issue causes, and "
                    "approve explicitly when nothing blocks."
                ),
            },
            {
                "name": "Tester",
                "team_role": AgentTeamMember.Role.TESTER,
                "tools": ["read_file", "write_file", "execute_code"],
                "role_description": (
                    "You design and run tests. Cover the happy path, the edge cases, "
                    "and the failure modes; report results with the exact inputs and "
                    "outputs observed, never a bare pass/fail."
                ),
            },
        ],
    },
    "marketing": {
        "label": "Marketing team",
        "description": "Research audiences, draft copy, and polish it for publishing.",
        "team_name": "Marketing team",
        "collaboration_pattern": AgentTeam.CollaborationPattern.SEQUENTIAL,
        "coworkers": [
            {
                "name": "Market Researcher",
                "team_role": AgentTeamMember.Role.RESEARCHER,
                "tools": ["web_search", "read_webpage", "write_file"],
                "role_description": (
                    "You research markets, audiences, and competitors. Cite where "
                    "each claim comes from, separate facts from interpretation, and "
                    "end with the three findings that matter most."
                ),
            },
            {
                "name": "Copywriter",
                "team_role": AgentTeamMember.Role.WRITER,
                "tools": ["web_search", "read_webpage", "read_file", "write_file"],
                "role_description": (
                    "You write marketing copy grounded in the research you are "
                    "given. Match the requested tone and channel, lead with the "
                    "benefit, and offer two variants when the ask is open-ended."
                ),
            },
            {
                "name": "Editor",
                "team_role": AgentTeamMember.Role.REVIEWER,
                "tools": ["read_file"],
                "role_description": (
                    "You edit for clarity, accuracy, and brand voice. Cut filler, "
                    "fix structure before sentences, and return a publish-ready "
                    "draft plus a short list of what you changed and why."
                ),
            },
        ],
    },
    "operations": {
        "label": "Operations team",
        "description": "Research options, document processes, and keep work moving.",
        "team_name": "Operations team",
        "collaboration_pattern": AgentTeam.CollaborationPattern.MANAGER_DELEGATE,
        "coworkers": [
            {
                "name": "Ops Manager",
                "team_role": AgentTeamMember.Role.MANAGER,
                "tools": ["web_search", "read_webpage", "read_file", "write_file"],
                "role_description": (
                    "You coordinate operational work. Turn fuzzy requests into "
                    "checklists with owners and deadlines, delegate the pieces, and "
                    "summarize status so a busy human can act on it in one read."
                ),
            },
            {
                "name": "Research Analyst",
                "team_role": AgentTeamMember.Role.RESEARCHER,
                "tools": ["web_search", "read_webpage", "write_file"],
                "role_description": (
                    "You compare vendors, tools, and options. Build small decision "
                    "tables with criteria that matter, note pricing and risks, and "
                    "make one clear recommendation."
                ),
            },
            {
                "name": "Process Writer",
                "team_role": AgentTeamMember.Role.WRITER,
                "tools": ["read_file", "write_file"],
                "role_description": (
                    "You document processes as step-by-step runbooks someone new "
                    "could follow. Number the steps, state the expected result of "
                    "each, and call out the failure points."
                ),
            },
        ],
    },
    "solo": {
        "label": "Solo assistant",
        "description": "One capable generalist to start with — specialize it later.",
        "team_name": "",
        "collaboration_pattern": "",
        "coworkers": [
            {
                "name": "Assistant",
                "team_role": AgentTeamMember.Role.CUSTOM,
                "custom_role_label": "Generalist",
                "tools": ["web_search", "read_webpage", "read_file", "write_file", "execute_code"],
                "role_description": (
                    "You are a helpful, general-purpose coworker. You can research, "
                    "draft, summarize, analyze, and use the tools attached to you to "
                    "get work done. Ask for clarification when a request is "
                    "ambiguous, and keep answers concise."
                ),
            },
        ],
    },
}


def template_catalog() -> list[dict[str, Any]]:
    """Public listing shape for GET /team-templates."""
    return [
        {
            "key": key,
            "label": template["label"],
            "description": template["description"],
            "coworkers": [
                {"name": member["name"], "role_description": member["role_description"]}
                for member in template["coworkers"]
            ],
        }
        for key, template in TEMPLATES.items()
    ]


def _clean_spec(spec: dict[str, Any]) -> dict[str, Any]:
    coworkers = spec.get("coworkers") or []
    if not coworkers:
        raise ValidationError({"coworkers": "At least one coworker is required."})
    if len(coworkers) > MAX_TEAM_SIZE:
        raise ValidationError({"coworkers": f"A starter team is capped at {MAX_TEAM_SIZE} coworkers."})
    cleaned = []
    for member in coworkers:
        name = str(member.get("name", "")).strip()
        role_description = str(member.get("role_description", "")).strip()
        if not name or not role_description:
            raise ValidationError(
                {"coworkers": "Every coworker needs a name and a role_description."}
            )
        team_role = member.get("team_role", AgentTeamMember.Role.CUSTOM)
        if team_role not in AgentTeamMember.Role.values:
            team_role = AgentTeamMember.Role.CUSTOM
        cleaned.append(
            {
                "name": name[:255],
                "role_description": role_description,
                "team_role": team_role,
                "custom_role_label": str(member.get("custom_role_label", ""))[:100],
                "tools": [str(tool) for tool in member.get("tools") or []],
            }
        )
    return {
        "team_name": str(spec.get("team_name", "")).strip()[:255],
        "collaboration_pattern": spec.get("collaboration_pattern", ""),
        "coworkers": cleaned,
    }


def provision_team(
    *, workspace: Workspace, created_by: User, spec: dict[str, Any]
) -> dict[str, Any]:
    """Create the spec's coworkers (+tools), and an agent team when it makes
    sense (2+ members and a valid pattern). Single transaction: a bad spec
    leaves nothing half-created."""
    cleaned = _clean_spec(spec)
    tools_by_name = {tool.name: tool for tool in Tool.objects.all()}

    with transaction.atomic():
        created: list[tuple[Coworker, dict[str, Any]]] = []
        for member in cleaned["coworkers"]:
            coworker = create_coworker(
                workspace=workspace,
                owner=created_by,
                owner_type=Coworker.OwnerType.USER,
                name=member["name"],
                role_description=member["role_description"],
                model_binding=dict(DEFAULT_MODEL_BINDING),
                created_by=created_by,
            )
            tool_names = list(member["tools"])
            # Managers (and a solo coworker) also get the orchestration
            # tools, so the workspace can be driven from a chat with them.
            if member["team_role"] == AgentTeamMember.Role.MANAGER or len(cleaned["coworkers"]) == 1:
                tool_names += [name for name in ORCHESTRATION_TOOLS if name not in tool_names]
            for tool_name in tool_names:
                tool = tools_by_name.get(tool_name)
                if tool is not None:
                    coworker.tool_attachments.create(tool=tool)
            created.append((coworker, member))

        team = None
        pattern = cleaned["collaboration_pattern"]
        if len(created) >= 2 and pattern in AgentTeam.CollaborationPattern.values:
            team = create_agent_team(
                workspace=workspace,
                user=created_by,
                payload={
                    "name": cleaned["team_name"] or "Starter team",
                    "collaboration_pattern": pattern,
                    "members": [
                        {
                            "coworker_id": str(coworker.id),
                            "role": member["team_role"],
                            "custom_role_label": member["custom_role_label"],
                        }
                        for coworker, member in created
                    ],
                },
            )

    return {
        "coworkers": [
            {"id": str(coworker.id), "name": coworker.name} for coworker, _ in created
        ],
        "team_id": str(team.id) if team else None,
        "team_name": team.name if team else None,
    }


def provision_template(
    *, workspace: Workspace, created_by: User, template_key: str
) -> dict[str, Any]:
    template = TEMPLATES.get(template_key)
    if template is None:
        raise ValidationError({"template": f"Unknown starter template {template_key!r}."})
    return provision_team(workspace=workspace, created_by=created_by, spec=template)
