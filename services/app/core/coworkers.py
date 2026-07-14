"""
Coworker creation/versioning/rollback — kept out of views.py so the "editing
a coworker always creates a new version" and "rollback is itself a recorded
version, not a destructive pointer move" rules live in exactly one place,
per IMPLEMENTATION_PLAN.md Milestone 3 Epic 3.1.
"""

from __future__ import annotations

from core.models import Coworker, CoworkerVersion, PermissionProfile, User, Workspace

DEFAULT_PERMISSION_PROFILE_NAME = "Default"


def get_or_create_default_permission_profile(workspace: Workspace) -> PermissionProfile:
    profile, _ = PermissionProfile.objects.get_or_create(
        workspace=workspace, name=DEFAULT_PERMISSION_PROFILE_NAME
    )
    return profile


def create_coworker(
    *,
    workspace: Workspace,
    owner: User | None = None,
    owner_type: str = Coworker.OwnerType.USER,
    owner_id=None,
    name: str,
    role_description: str,
    model_binding: dict,
    created_by: User,
    avatar_url: str | None = None,
    permission_profile: PermissionProfile | None = None,
) -> Coworker:
    resolved_owner_id = owner_id or (owner.id if owner else None)
    if owner_type not in Coworker.OwnerType.values or resolved_owner_id is None:
        raise ValueError("A valid coworker owner type and owner id are required.")
    coworker = Coworker.objects.create(
        workspace=workspace,
        owner_type=owner_type,
        owner_id=resolved_owner_id,
        name=name,
        avatar_url=avatar_url,
    )
    resolved_permission_profile = permission_profile or get_or_create_default_permission_profile(
        workspace
    )
    version = CoworkerVersion.objects.create(
        coworker=coworker,
        version_number=1,
        role_description=role_description,
        model_binding=model_binding,
        permission_profile=resolved_permission_profile,
        created_by=created_by,
    )
    coworker.current_version = version
    coworker.save(update_fields=["current_version", "updated_at"])
    return coworker


def create_new_version(
    coworker: Coworker,
    *,
    created_by: User,
    role_description: str | None = None,
    model_binding: dict | None = None,
    permission_profile: PermissionProfile | None = None,
    changelog: str | None = None,
) -> CoworkerVersion:
    """Used for both a normal edit (PATCH) and to bring name/avatar_url up
    to date — role_description/model_binding/permission_profile default to
    the current version's values when not explicitly changing."""
    current = coworker.current_version
    next_number = (current.version_number if current else 0) + 1
    version = CoworkerVersion.objects.create(
        coworker=coworker,
        version_number=next_number,
        role_description=(
            role_description if role_description is not None else current.role_description
        ),
        model_binding=model_binding if model_binding is not None else current.model_binding,
        permission_profile=permission_profile or current.permission_profile,
        created_by=created_by,
        changelog=changelog,
    )
    coworker.current_version = version
    coworker.save(update_fields=["current_version", "updated_at"])
    return version


def rollback_to_version(
    coworker: Coworker, target_version: CoworkerVersion, *, created_by: User
) -> CoworkerVersion:
    """Rollback creates a NEW version copying the target's content, rather
    than moving current_version backward — history only ever grows forward,
    so "what was active when" stays answerable from version_number alone."""
    return create_new_version(
        coworker,
        created_by=created_by,
        role_description=target_version.role_description,
        model_binding=target_version.model_binding,
        permission_profile=target_version.permission_profile,
        changelog=f"Rolled back to v{target_version.version_number}",
    )
