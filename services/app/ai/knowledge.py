from __future__ import annotations

import io
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.utils import timezone
from pgvector.django import CosineDistance

from ai.embeddings import embed_text
from ai.models import (
    CoworkerKnowledgeBaseAttachment,
    KnowledgeChunk,
    KnowledgeDocument,
)


def _s3_client():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=settings.MINIO_ENDPOINT,
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
        use_ssl=settings.MINIO_SECURE,
    )


def store_upload(key: str, data: bytes, content_type: str) -> None:
    try:
        client = _s3_client()
        try:
            client.head_bucket(Bucket=settings.MINIO_BUCKET)
        except Exception:
            client.create_bucket(Bucket=settings.MINIO_BUCKET)
        client.put_object(
            Bucket=settings.MINIO_BUCKET, Key=key, Body=data, ContentType=content_type
        )
    except Exception:
        path = Path(settings.KNOWLEDGE_FILES_ROOT) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def load_upload(key: str) -> bytes:
    try:
        response = _s3_client().get_object(Bucket=settings.MINIO_BUCKET, Key=key)
        return response["Body"].read()
    except Exception:
        return (Path(settings.KNOWLEDGE_FILES_ROOT) / key).read_bytes()


def extract_text(data: bytes, mime_type: str, filename: str) -> str:
    if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
        from pypdf import PdfReader
        return "\n\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    return data.decode("utf-8", errors="replace")


def chunk_text(text: str, target_words: int = 350, overlap: int = 50) -> list[str]:
    words = text.split()
    if not words:
        return []
    step = max(1, target_words - overlap)
    return [" ".join(words[start : start + target_words]) for start in range(0, len(words), step)]


def ingest_document(document_id: UUID | str) -> None:
    document = KnowledgeDocument.objects.get(id=document_id)
    try:
        document.ingestion_status = KnowledgeDocument.IngestionStatus.CHUNKING
        document.ingestion_error = ""
        document.save(update_fields=["ingestion_status", "ingestion_error"])
        text = extract_text(
            load_upload(document.object_storage_key), document.mime_type, document.source_uri
        )
        chunks = chunk_text(text)
        if not chunks:
            raise ValueError("No readable text was found in this document.")
        document.ingestion_status = KnowledgeDocument.IngestionStatus.EMBEDDING
        document.save(update_fields=["ingestion_status"])
        KnowledgeChunk.objects.filter(document=document).delete()
        KnowledgeChunk.objects.bulk_create(
            [
                KnowledgeChunk(
                    document=document,
                    chunk_index=index,
                    content=content,
                    embedding=embed_text(content),
                    token_count=len(content.split()),
                )
                for index, content in enumerate(chunks)
            ]
        )
        document.ingestion_status = KnowledgeDocument.IngestionStatus.READY
        document.last_crawled_at = timezone.now()
        document.save(update_fields=["ingestion_status", "last_crawled_at"])
    except Exception as exc:
        document.ingestion_status = KnowledgeDocument.IngestionStatus.FAILED
        document.ingestion_error = str(exc)[:2000]
        document.save(update_fields=["ingestion_status", "ingestion_error"])
        raise


def search_coworker_knowledge(
    *, coworker_id: UUID | str, query: str, limit: int = 5
) -> list[KnowledgeChunk]:
    kb_ids = CoworkerKnowledgeBaseAttachment.objects.filter(
        coworker_id=coworker_id
    ).values_list("knowledge_base_id", flat=True)
    return list(
        KnowledgeChunk.objects.filter(
            document__knowledge_base_id__in=kb_ids,
            document__ingestion_status=KnowledgeDocument.IngestionStatus.READY,
        )
        .select_related("document", "document__knowledge_base")
        .alias(distance=CosineDistance("embedding", embed_text(query)))
        .order_by("distance")[:limit]
    )
