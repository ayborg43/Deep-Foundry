from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ManifestError(ValueError):
    pass


LISTING_TYPES = {"skill", "capability_pack", "workflow_template"}


def load_manifest(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"Could not read {source}: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError("The manifest root must be a JSON object.")
    return data


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    for key in ("name", "version", "listing_type", "summary"):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            errors.append(f"{key} must be a non-empty string")
    if manifest.get("listing_type") not in LISTING_TYPES:
        errors.append(f"listing_type must be one of {sorted(LISTING_TYPES)}")
    tools = manifest.get("declared_tools", [])
    if not isinstance(tools, list) or any(not isinstance(item, (str, dict)) for item in tools):
        errors.append("declared_tools must be an array of tool names or objects")
    if manifest.get("listing_type") == "skill" and not manifest.get("instructions_file"):
        errors.append("skills require instructions_file")
    if errors:
        raise ManifestError("; ".join(errors))
    return manifest
