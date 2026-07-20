"""Provision user-designed coworker teams.

The built-in starter catalog is intentionally empty. Existing coworkers are
database records owned by users and are never modified here. Keeping the
catalog and provisioning interfaces in place makes it straightforward to add
the project's new reviewed template later.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from rest_framework.exceptions import ValidationError

from core.coworkers import create_coworker
from core.models import AgentTeam, AgentTeamMember, Coworker, Tool, User, Workspace
from core.provisioning import DEFAULT_MODEL_BINDING
from core.v2_services import create_agent_team

MAX_TEAM_SIZE = 6

ORCHESTRATION_TOOLS = (
    "workspace_status",
    "create_coworker",
    "create_agent_team",
    "run_agent_team",
    "create_task",
    "schedule_workflow",
)

# No platform-supplied coworker templates. Add the new project template here
# only after its requirements have been agreed with the user.
TEMPLATES: dict[str, dict[str, Any]] = {}


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
        raise ValidationError(
            {"coworkers": f"A starter team is capped at {MAX_TEAM_SIZE} coworkers."}
        )
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
    """Create user-designed coworkers and, for multi-member specs, a team."""
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
            if "web_search" in tool_names:
                tool_names += [
                    name
                    for name in (
                        "read_webpage",
                        "read_document",
                        "crawl_website",
                        "extract_structured_data",
                    )
                    if name not in tool_names
                ]
            if (
                member["team_role"] == AgentTeamMember.Role.MANAGER
                or len(cleaned["coworkers"]) == 1
            ):
                tool_names += [
                    name for name in ORCHESTRATION_TOOLS if name not in tool_names
                ]
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
