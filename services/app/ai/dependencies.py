"""
FastAPI-side auth for the AI modules. Mirrors the Core modules' DRF auth
(same JWTs, same workspace-membership rule) but implemented natively for
FastAPI since these endpoints aren't DRF views — per ARCHITECTURE.md §7,
it's still one Security & Permissions rule (workspace membership via
core.permissions), just invoked from a different entrypoint.

Django's ORM refuses synchronous calls made directly from an async context
(SynchronousOnlyOperation) — every call into Core here goes through
asgiref's sync_to_async so it runs in a worker thread instead.
"""

from asgiref.sync import sync_to_async
from fastapi import Header, HTTPException
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from core.models import User, Workspace
from core.permissions import get_workspace_for_member


async def get_current_user(authorization: str | None = Header(default=None)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token_string = authorization.removeprefix("Bearer ").strip()
    try:
        token = AccessToken(token_string)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc

    try:
        return await sync_to_async(User.objects.get)(id=token["user_id"])
    except User.DoesNotExist as exc:
        raise HTTPException(status_code=401, detail="User not found") from exc


async def require_workspace_member(workspace_id: str, user: User) -> Workspace:
    try:
        return await sync_to_async(get_workspace_for_member)(user, workspace_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
