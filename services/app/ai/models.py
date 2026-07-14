"""
AI-module models per DATABASE.md §3: model_calls (§3.4, Milestone 2) and
conversations/conversation_participants/messages (§3.3, Milestone 4).

`ai` is a distinct Django app (not merged into `core`) specifically so the
`core`/`ai` "logical schema" boundary from DATABASE.md §1 has a real
enforcement mechanism (separate model registries, separate migration
histories) rather than being just a naming convention — consistent with
ARCHITECTURE.md ADR-006 treating the Core/AI split as a code-organization
seam even though both run in one process.
"""

from django.db import models
from pgvector.django import HnswIndex, VectorField

from core.models import Coworker, ProviderCredential, User, UUIDPrimaryKeyModel, Workspace


class ModelCall(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        ERROR = "error", "Error"
        RATE_LIMITED = "rate_limited", "Rate limited"

    request_id = models.UUIDField()
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="model_calls")
    # Real FK since Milestone 4 — the Coworker model didn't exist until
    # Milestone 3, so this was a plain UUIDField before that.
    coworker = models.ForeignKey(
        Coworker, on_delete=models.SET_NULL, null=True, blank=True, related_name="model_calls"
    )
    deployment_mode = models.CharField(
        max_length=30, choices=ProviderCredential.DeploymentMode.choices
    )
    model_id = models.CharField(max_length=100)
    capability_requested = models.JSONField(default=dict, blank=True)
    fallback_used = models.BooleanField(default=False)
    input_tokens = models.IntegerField(null=True, blank=True)
    output_tokens = models.IntegerField(null=True, blank=True)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    latency_ms = models.IntegerField()
    status = models.CharField(max_length=20, choices=Status.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "model_calls"
        indexes = [models.Index(fields=["workspace", "created_at"])]

    def __str__(self) -> str:
        return f"{self.model_id} ({self.status}) @ {self.created_at}"


class Conversation(UUIDPrimaryKeyModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="conversations")
    # No FK — the Project model doesn't exist yet (not scoped into any
    # milestone through Milestone 4), same treatment as Coworker.owner_id
    # before Coworker existed.
    project_id = models.UUIDField(null=True, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    title = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "conversations"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title or str(self.id)


class ConversationParticipant(UUIDPrimaryKeyModel):
    class ParticipantType(models.TextChoices):
        USER = "user", "User"
        COWORKER = "coworker", "Coworker"

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="participants"
    )
    participant_type = models.CharField(max_length=20, choices=ParticipantType.choices)
    # Polymorphic per DATABASE.md §3.3 — no FK, same pattern as Coworker.owner_id.
    participant_id = models.UUIDField()

    class Meta:
        db_table = "conversation_participants"
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "participant_type", "participant_id"],
                name="uniq_conversation_participant",
            )
        ]


class Message(UUIDPrimaryKeyModel):
    class SenderType(models.TextChoices):
        USER = "user", "User"
        COWORKER = "coworker", "Coworker"
        SYSTEM = "system", "System"

    class Status(models.TextChoices):
        # Not a DATABASE.md §3.3 column — added in Milestone 4 so the stream
        # endpoint knows which message is still in flight (and the approval
        # gate has somewhere to park "blocked mid-generation").
        PENDING = "pending", "Pending"
        STREAMING = "streaming", "Streaming"
        NEEDS_APPROVAL = "needs_approval", "Needs approval"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    sender_type = models.CharField(max_length=20, choices=SenderType.choices)
    sender_id = models.UUIDField(null=True, blank=True)
    content = models.TextField(blank=True)
    tool_calls = models.JSONField(null=True, blank=True)
    # Not a DATABASE.md §3.3 column — added in Milestone 4. Set on a
    # SYSTEM-sender message that carries a tool's result: the wire format
    # DeepSeek's API requires (OpenAI-compatible) needs a role="tool" message
    # tagged with the specific tool_call_id it's answering, so replaying
    # conversation history back to the model on a follow-up call is lossy
    # without storing which call this result belongs to.
    tool_call_id = models.CharField(max_length=255, null=True, blank=True)
    parent_message = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="regenerations"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COMPLETE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "messages"
        ordering = ["created_at"]
        constraints = [
            # Defense-in-depth alongside chat_orchestrator's row-locking:
            # at most one result per (parent message, tool call) — a second
            # concurrent attempt to store a result for the same call fails
            # at the database level rather than silently double-executing.
            models.UniqueConstraint(
                fields=["parent_message", "tool_call_id"],
                condition=models.Q(tool_call_id__isnull=False),
                name="uniq_tool_result_per_call",
            )
        ]

    def __str__(self) -> str:
        return f"{self.sender_type}:{self.id}"


class KnowledgeBase(UUIDPrimaryKeyModel):
    class Scope(models.TextChoices):
        COWORKER = "coworker", "Coworker"
        PROJECT = "project", "Project"
        WORKSPACE = "workspace", "Workspace"

    class SourceType(models.TextChoices):
        DOCUMENT = "document", "Document"
        URL = "url", "URL"
        SPREADSHEET = "spreadsheet", "Spreadsheet"
        DATABASE = "database", "Database"
        CONVERSATION = "conversation", "Conversation"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="knowledge_bases")
    scope = models.CharField(max_length=20, choices=Scope.choices)
    scope_id = models.UUIDField()
    name = models.CharField(max_length=255)
    source_type = models.CharField(
        max_length=20, choices=SourceType.choices, default=SourceType.DOCUMENT
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "knowledge_bases"
        ordering = ["-created_at"]


class KnowledgeDocument(UUIDPrimaryKeyModel):
    class IngestionStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        CHUNKING = "chunking", "Chunking"
        EMBEDDING = "embedding", "Embedding"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    knowledge_base = models.ForeignKey(
        KnowledgeBase, on_delete=models.CASCADE, related_name="documents"
    )
    source_uri = models.TextField()
    mime_type = models.CharField(max_length=255)
    object_storage_key = models.TextField()
    ingestion_status = models.CharField(
        max_length=20, choices=IngestionStatus.choices, default=IngestionStatus.PENDING
    )
    ingestion_error = models.TextField(blank=True)
    last_crawled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "knowledge_documents"
        ordering = ["-created_at"]


class CoworkerKnowledgeBaseAttachment(UUIDPrimaryKeyModel):
    coworker = models.ForeignKey(
        Coworker, on_delete=models.CASCADE, related_name="knowledge_base_attachments"
    )
    knowledge_base = models.ForeignKey(
        KnowledgeBase, on_delete=models.CASCADE, related_name="coworker_attachments"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "coworker_knowledge_base_attachments"
        constraints = [
            models.UniqueConstraint(
                fields=["coworker", "knowledge_base"], name="uniq_coworker_knowledge_base"
            )
        ]


class KnowledgeChunk(UUIDPrimaryKeyModel):
    document = models.ForeignKey(
        KnowledgeDocument, on_delete=models.CASCADE, related_name="chunks"
    )
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    embedding = VectorField(dimensions=1536)
    token_count = models.PositiveIntegerField()

    class Meta:
        db_table = "knowledge_chunks"
        constraints = [
            models.UniqueConstraint(fields=["document", "chunk_index"], name="uniq_document_chunk")
        ]
        indexes = [
            HnswIndex(
                name="knowledge_chunk_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            )
        ]


class MemoryEntry(UUIDPrimaryKeyModel):
    class Scope(models.TextChoices):
        USER = "user", "User"
        COWORKER = "coworker", "Coworker"
        PROJECT = "project", "Project"
        ORGANIZATION = "organization", "Organization"
        TEMPORARY = "temporary", "Temporary"

    class SourceType(models.TextChoices):
        CONVERSATION = "conversation", "Conversation"
        TASK_RESULT = "task_result", "Task result"
        MANUAL = "manual", "Manual"
        WORKFLOW_RUN = "workflow_run", "Workflow run"

    scope = models.CharField(max_length=20, choices=Scope.choices)
    scope_id = models.UUIDField()
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memory_entries")
    content = models.TextField()
    embedding = VectorField(dimensions=1536)
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    source_ref_id = models.UUIDField(null=True, blank=True)
    is_long_term = models.BooleanField(default=False)
    promoted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "memory_entries"
        ordering = ["-created_at"]
        indexes = [
            HnswIndex(
                name="memory_entry_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            )
        ]
