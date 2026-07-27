"""Turn a plain-English edit instruction into proposed changes to a coworker's
config. This proposes only — it never writes to the database. The caller
reviews the proposal and saves it through the normal PATCH / tool-attach
endpoints, so a human stays in the loop on every change.
"""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from ai.model_router.adapters.deepseek_cloud import _MODEL_CAPABILITIES
from ai.model_router.factory import build_model_router
from ai.model_router.types import ChatMessage, ModelConfig
from core.models import Coworker, CoworkerToolAttachment, Tool

VALID_MODELS = set(_MODEL_CAPABILITIES)


class CoworkerEditError(Exception):
    """The instruction couldn't be turned into a usable edit proposal."""


_SYSTEM_PROMPT = """You revise one AI coworker's configuration from a plain-English instruction.

Return ONLY a JSON object, no prose, containing just the fields that should
change (omit anything the instruction doesn't touch):
{{
  "name": "new name",                     // only if renaming
  "role_description": "full new text",    // the COMPLETE rewritten role, not a diff
  "model": one of {models},               // only if switching model
  "add_tools": ["tool names from the catalog"],
  "remove_tools": ["names of currently-attached tools to drop"],
  "summary": "one short sentence describing the change"
}}

Rules:
- role_description, when present, is the complete replacement text.
- Only use tool names from this catalog: {tools}
- Never invent tools or models. Leave a field out if it isn't changing."""


def _extract_json(text: str) -> dict[str, Any]:
    candidate = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.DOTALL)
    if fenced:
        candidate = fenced.group(1)
    else:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            raise CoworkerEditError("The model did not return an edit proposal.")
        candidate = candidate[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise CoworkerEditError("The model returned malformed JSON.") from exc
    if not isinstance(parsed, dict):
        raise CoworkerEditError("The proposal was not a JSON object.")
    return parsed


def _sanitize(parsed: dict[str, Any], *, catalog: set[str], attached: set[str]) -> dict[str, Any]:
    """Keep only well-formed, real values — drop hallucinated tools/models."""
    out: dict[str, Any] = {}
    name = parsed.get("name")
    if isinstance(name, str) and name.strip():
        out["name"] = name.strip()[:255]
    role = parsed.get("role_description")
    if isinstance(role, str) and role.strip():
        out["role_description"] = role.strip()
    if parsed.get("model") in VALID_MODELS:
        out["model"] = parsed["model"]
    add = [
        t for t in parsed.get("add_tools") or []
        if isinstance(t, str) and t in catalog and t not in attached
    ]
    remove = [
        t for t in parsed.get("remove_tools") or []
        if isinstance(t, str) and t in attached
    ]
    if add:
        out["add_tools"] = sorted(set(add))
    if remove:
        out["remove_tools"] = sorted(set(remove))
    summary = parsed.get("summary")
    out["summary"] = summary.strip()[:200] if isinstance(summary, str) else ""
    return out


def suggest_edit(*, workspace_id: UUID | str, coworker_id: UUID | str, instruction: str) -> dict[str, Any]:
    """Propose config changes for a coworker from a natural-language instruction.

    Raises CoworkerEditError (unusable input/output), CredentialNotFoundError
    (no provider key), or AdapterError (model failure) — callers map to HTTP."""
    instruction = (instruction or "").strip()
    if not instruction:
        raise CoworkerEditError("Describe what you'd like to change.")

    coworker = Coworker.objects.filter(id=coworker_id).select_related("current_version").first()
    if coworker is None:
        raise CoworkerEditError("Coworker not found.")
    current = coworker.current_version
    attached = list(
        CoworkerToolAttachment.objects.filter(coworker=coworker)
        .select_related("tool")
        .values_list("tool__name", flat=True)
    )
    catalog = list(Tool.objects.values_list("name", flat=True))

    prompt = _SYSTEM_PROMPT.format(
        models=json.dumps(sorted(VALID_MODELS)),
        tools=json.dumps(sorted(catalog)),
    )
    context = {
        "name": coworker.name,
        "role_description": current.role_description if current else "",
        "model": (current.model_binding or {}).get("primary") if current else None,
        "attached_tools": attached,
    }
    router = build_model_router(workspace_id=workspace_id)
    response = router.generate(
        [
            ChatMessage(role="system", content=prompt),
            ChatMessage(
                role="user",
                content="Current config:\n" + json.dumps(context) + "\n\nInstruction:\n" + instruction,
            ),
        ],
        [],
        ModelConfig(model_id="deepseek-v4-flash", temperature=0.2),
        fallback_model_id="deepseek-v4-pro",
    )
    return _sanitize(_extract_json(response.content), catalog=set(catalog), attached=set(attached))
