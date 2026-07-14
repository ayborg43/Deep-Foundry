from unittest.mock import patch

from django.test import TestCase

from ai.embeddings import EMBEDDING_DIMENSIONS, embed_text
from ai.knowledge import chunk_text, ingest_document
from ai.memory import search_memory, write_memory
from ai.models import KnowledgeBase, KnowledgeDocument, MemoryEntry
from core.models import User, Workspace, WorkspaceMember


class EmbeddingAndChunkingTests(TestCase):
    def test_embedding_is_stable_normalized_and_has_documented_dimensions(self):
        first = embed_text("The customer prefers weekly reports")
        second = embed_text("The customer prefers weekly reports")
        self.assertEqual(first, second)
        self.assertEqual(len(first), EMBEDDING_DIMENSIONS)
        self.assertAlmostEqual(sum(value * value for value in first), 1.0)

    def test_chunking_preserves_overlap(self):
        chunks = chunk_text("one two three four five six", target_words=4, overlap=2)
        self.assertEqual(chunks, ["one two three four", "three four five six", "five six"])


class MemoryAndIngestionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="memory@example.com", password="safe password 123")
        self.workspace = Workspace.objects.create(
            name="Memory", type=Workspace.WorkspaceType.PERSONAL, owner=self.user
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace, user=self.user, role=WorkspaceMember.Role.OWNER
        )

    def test_memory_write_and_semantic_search(self):
        write_memory(
            workspace_id=self.workspace.id, scope=MemoryEntry.Scope.COWORKER,
            scope_id=self.user.id, content="Preferred weekly report format is PDF",
        )
        write_memory(
            workspace_id=self.workspace.id, scope=MemoryEntry.Scope.COWORKER,
            scope_id=self.user.id, content="The office is closed on Friday",
        )
        results = search_memory(
            workspace_id=self.workspace.id, scope=MemoryEntry.Scope.COWORKER,
            scope_id=self.user.id, query="weekly PDF report", limit=1,
        )
        self.assertEqual(results[0].content, "Preferred weekly report format is PDF")

    @patch("ai.knowledge.load_upload", return_value=b"Agentarium knowledge answer is cobalt blue.")
    def test_document_ingestion_chunks_embeds_and_marks_ready(self, _load_upload):
        kb = KnowledgeBase.objects.create(
            workspace=self.workspace, scope=KnowledgeBase.Scope.WORKSPACE,
            scope_id=self.workspace.id, name="Reference",
        )
        document = KnowledgeDocument.objects.create(
            knowledge_base=kb, source_uri="reference.txt", mime_type="text/plain",
            object_storage_key="test/reference.txt",
        )
        ingest_document(document.id)
        document.refresh_from_db()
        self.assertEqual(document.ingestion_status, KnowledgeDocument.IngestionStatus.READY)
        chunk = document.chunks.get()
        self.assertIn("cobalt blue", chunk.content)
        self.assertEqual(len(chunk.embedding), EMBEDDING_DIMENSIONS)
