from __future__ import annotations

from uuid import UUID

from django.utils import timezone
from pgvector.django import CosineDistance

from ai.embeddings import embed_text
from ai.models import MemoryEntry


def write_memory(
    *, workspace_id: UUID | str, scope: str, scope_id: UUID | str, content: str,
    source_type: str = MemoryEntry.SourceType.MANUAL,
    source_ref_id: UUID | str | None = None, is_long_term: bool = True,
) -> MemoryEntry:
    return MemoryEntry.objects.create(
        workspace_id=workspace_id,
        scope=scope,
        scope_id=scope_id,
        content=content.strip(),
        embedding=embed_text(content),
        source_type=source_type,
        source_ref_id=source_ref_id,
        is_long_term=is_long_term,
        promoted_at=timezone.now() if is_long_term else None,
    )


def search_memory(
    *, workspace_id: UUID | str, scope: str, scope_id: UUID | str,
    query: str, limit: int = 5,
) -> list[MemoryEntry]:
    return list(
        MemoryEntry.objects.filter(
            workspace_id=workspace_id, scope=scope, scope_id=scope_id, is_long_term=True
        )
        .alias(distance=CosineDistance("embedding", embed_text(query)))
        .order_by("distance")[:limit]
    )


def remember_conversation_turn(
    *, workspace_id: UUID | str, coworker_id: UUID | str,
    conversation_id: UUID | str, user_content: str, assistant_content: str,
) -> MemoryEntry | None:
    user_content = user_content.strip()
    if not user_content:
        return None
    # A concise, inspectable turn summary. Keeping the user's statement first
    # makes preference/fact recall useful while avoiding a hidden LLM call.
    summary = f"User: {user_content[:1200]}"
    if assistant_content.strip():
        summary += f"\nCoworker response: {assistant_content.strip()[:800]}"
    return write_memory(
        workspace_id=workspace_id,
        scope=MemoryEntry.Scope.COWORKER,
        scope_id=coworker_id,
        content=summary,
        source_type=MemoryEntry.SourceType.CONVERSATION,
        source_ref_id=conversation_id,
        is_long_term=True,
    )
