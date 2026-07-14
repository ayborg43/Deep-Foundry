from __future__ import annotations

from uuid import uuid4

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from ai.embeddings import embed_text
from ai.knowledge import store_upload
from ai.memory import search_memory, write_memory
from ai.models import (
    CoworkerKnowledgeBaseAttachment,
    KnowledgeBase,
    KnowledgeDocument,
    MemoryEntry,
)
from core.interface import write_audit_log
from core.models import Coworker
from core.permissions import get_coworker_for_member, get_workspace_for_member
from worker.tasks import ingest_knowledge_document


def _memory_data(entry: MemoryEntry) -> dict:
    return {
        "id": str(entry.id), "workspace_id": str(entry.workspace_id),
        "scope": entry.scope, "scope_id": str(entry.scope_id), "content": entry.content,
        "source_type": entry.source_type,
        "source_ref_id": str(entry.source_ref_id) if entry.source_ref_id else None,
        "is_long_term": entry.is_long_term,
        "promoted_at": entry.promoted_at, "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


def _kb_data(kb: KnowledgeBase, include_documents: bool = False) -> dict:
    data = {
        "id": str(kb.id), "workspace_id": str(kb.workspace_id), "scope": kb.scope,
        "scope_id": str(kb.scope_id), "name": kb.name,
        "source_type": kb.source_type, "created_at": kb.created_at,
        "attached_coworker_ids": [str(value) for value in kb.coworker_attachments.values_list("coworker_id", flat=True)],
    }
    if include_documents:
        data["documents"] = [_document_data(doc) for doc in kb.documents.all()]
    return data


def _document_data(doc: KnowledgeDocument) -> dict:
    return {
        "id": str(doc.id), "knowledge_base_id": str(doc.knowledge_base_id),
        "source_uri": doc.source_uri, "mime_type": doc.mime_type,
        "ingestion_status": doc.ingestion_status, "ingestion_error": doc.ingestion_error,
        "last_crawled_at": doc.last_crawled_at, "created_at": doc.created_at,
    }


def _memory_queryset_for_user(request: Request):
    workspace_ids = request.user.workspace_memberships.values_list("workspace_id", flat=True)
    return MemoryEntry.objects.filter(workspace_id__in=workspace_ids)


class MemoryListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        scope = request.query_params.get("scope")
        scope_id = request.query_params.get("scope_id")
        if not scope or not scope_id:
            raise ValidationError({"scope": "scope and scope_id are required."})
        queryset = _memory_queryset_for_user(request).filter(scope=scope, scope_id=scope_id)
        query = request.query_params.get("query", "").strip()
        if query:
            first = queryset.first()
            entries = search_memory(
                workspace_id=first.workspace_id, scope=scope, scope_id=scope_id, query=query
            ) if first else []
        else:
            entries = list(queryset.order_by("-created_at")[:100])
        return Response([_memory_data(entry) for entry in entries])

    def post(self, request: Request) -> Response:
        workspace = get_workspace_for_member(request.user, request.data.get("workspace_id"))
        scope = request.data.get("scope")
        scope_id = request.data.get("scope_id")
        content = str(request.data.get("content", "")).strip()
        if scope not in MemoryEntry.Scope.values or not scope_id or not content:
            raise ValidationError("workspace_id, valid scope, scope_id, and content are required.")
        if scope == MemoryEntry.Scope.COWORKER:
            coworker = get_coworker_for_member(request.user, scope_id)
            if coworker.workspace_id != workspace.id:
                raise ValidationError("Coworker is not in this workspace.")
        entry = write_memory(
            workspace_id=workspace.id, scope=scope, scope_id=scope_id, content=content,
            source_type=MemoryEntry.SourceType.MANUAL, is_long_term=True,
        )
        write_audit_log(
            actor_type="user", actor_id=request.user.id, action="memory.create",
            resource_type="memory_entry", resource_id=entry.id, workspace_id=workspace.id,
        )
        return Response(_memory_data(entry), status=status.HTTP_201_CREATED)


class MemoryDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _entry(self, request: Request, memory_id: str) -> MemoryEntry:
        return get_object_or_404(_memory_queryset_for_user(request), id=memory_id)

    def patch(self, request: Request, memory_id: str) -> Response:
        entry = self._entry(request, memory_id)
        content = str(request.data.get("content", "")).strip()
        if not content:
            raise ValidationError({"content": "This field is required."})
        entry.content = content
        entry.embedding = embed_text(content)
        entry.save(update_fields=["content", "embedding", "updated_at"])
        return Response(_memory_data(entry))

    def delete(self, request: Request, memory_id: str) -> Response:
        entry = self._entry(request, memory_id)
        entry.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MemoryTimelineView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, scope: str, scope_id: str) -> Response:
        entries = _memory_queryset_for_user(request).filter(
            scope=scope, scope_id=scope_id
        ).order_by("-created_at")[:200]
        return Response([_memory_data(entry) for entry in entries])


class KnowledgeBaseListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        workspace = get_workspace_for_member(request.user, request.query_params.get("workspace_id"))
        bases = KnowledgeBase.objects.filter(workspace=workspace).prefetch_related("coworker_attachments")
        return Response([_kb_data(kb) for kb in bases])

    def post(self, request: Request) -> Response:
        workspace = get_workspace_for_member(request.user, request.data.get("workspace_id"))
        scope = request.data.get("scope", KnowledgeBase.Scope.WORKSPACE)
        scope_id = request.data.get("scope_id", workspace.id)
        name = str(request.data.get("name", "")).strip()
        if not name or scope not in KnowledgeBase.Scope.values:
            raise ValidationError("name and a valid scope are required.")
        kb = KnowledgeBase.objects.create(
            workspace=workspace, scope=scope, scope_id=scope_id, name=name,
            source_type=KnowledgeBase.SourceType.DOCUMENT,
        )
        return Response(_kb_data(kb), status=status.HTTP_201_CREATED)


class KnowledgeBaseDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _kb(self, request: Request, kb_id: str) -> KnowledgeBase:
        kb = get_object_or_404(KnowledgeBase.objects.prefetch_related("documents", "coworker_attachments"), id=kb_id)
        get_workspace_for_member(request.user, kb.workspace_id)
        return kb

    def get(self, request: Request, kb_id: str) -> Response:
        return Response(_kb_data(self._kb(request, kb_id), include_documents=True))

    def delete(self, request: Request, kb_id: str) -> Response:
        self._kb(request, kb_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class KnowledgeDocumentUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request: Request, kb_id: str) -> Response:
        kb = get_object_or_404(KnowledgeBase, id=kb_id)
        get_workspace_for_member(request.user, kb.workspace_id)
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": "A document file is required."})
        if upload.size > 25 * 1024 * 1024:
            raise ValidationError({"file": "Files may not exceed 25 MB."})
        key = f"{kb.workspace_id}/{kb.id}/{uuid4()}-{upload.name}"
        store_upload(key, upload.read(), upload.content_type or "application/octet-stream")
        document = KnowledgeDocument.objects.create(
            knowledge_base=kb, source_uri=upload.name,
            mime_type=upload.content_type or "application/octet-stream", object_storage_key=key,
        )
        ingest_knowledge_document.delay(str(document.id))
        return Response(_document_data(document), status=status.HTTP_202_ACCEPTED)


class KnowledgeDocumentStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, kb_id: str, doc_id: str) -> Response:
        document = get_object_or_404(KnowledgeDocument, id=doc_id, knowledge_base_id=kb_id)
        get_workspace_for_member(request.user, document.knowledge_base.workspace_id)
        return Response(_document_data(document))


class CoworkerKnowledgeBaseAttachView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, coworker_id: str) -> Response:
        coworker = get_coworker_for_member(request.user, coworker_id, require_write=True)
        kb = get_object_or_404(KnowledgeBase, id=request.data.get("knowledge_base_id"), workspace=coworker.workspace)
        attachment, created = CoworkerKnowledgeBaseAttachment.objects.get_or_create(coworker=coworker, knowledge_base=kb)
        return Response({"id": str(attachment.id), "knowledge_base_id": str(kb.id)}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class CoworkerKnowledgeBaseDetachView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, coworker_id: str, kb_id: str) -> Response:
        coworker = get_coworker_for_member(request.user, coworker_id, require_write=True)
        get_object_or_404(CoworkerKnowledgeBaseAttachment, coworker=coworker, knowledge_base_id=kb_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
