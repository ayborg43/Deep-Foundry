import django.db.models.deletion
import pgvector.django
import uuid
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("ai", "0003_message_tool_call_id"), ("core", "0006_alter_auditlog_workspace")]

    operations = [
        pgvector.django.VectorExtension(),
        migrations.CreateModel(
            name="KnowledgeBase",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("scope", models.CharField(choices=[("coworker", "Coworker"), ("project", "Project"), ("workspace", "Workspace")], max_length=20)),
                ("scope_id", models.UUIDField()),
                ("name", models.CharField(max_length=255)),
                ("source_type", models.CharField(choices=[("document", "Document"), ("url", "URL"), ("spreadsheet", "Spreadsheet"), ("database", "Database"), ("conversation", "Conversation")], default="document", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="knowledge_bases", to="core.workspace")),
            ],
            options={"db_table": "knowledge_bases", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="MemoryEntry",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("scope", models.CharField(choices=[("user", "User"), ("coworker", "Coworker"), ("project", "Project"), ("organization", "Organization"), ("temporary", "Temporary")], max_length=20)),
                ("scope_id", models.UUIDField()),
                ("content", models.TextField()),
                ("embedding", pgvector.django.VectorField(dimensions=1536)),
                ("source_type", models.CharField(choices=[("conversation", "Conversation"), ("task_result", "Task result"), ("manual", "Manual"), ("workflow_run", "Workflow run")], max_length=20)),
                ("source_ref_id", models.UUIDField(blank=True, null=True)),
                ("is_long_term", models.BooleanField(default=False)),
                ("promoted_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memory_entries", to="core.workspace")),
            ],
            options={"db_table": "memory_entries", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="KnowledgeDocument",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("source_uri", models.TextField()),
                ("mime_type", models.CharField(max_length=255)),
                ("object_storage_key", models.TextField()),
                ("ingestion_status", models.CharField(choices=[("pending", "Pending"), ("chunking", "Chunking"), ("embedding", "Embedding"), ("ready", "Ready"), ("failed", "Failed")], default="pending", max_length=20)),
                ("ingestion_error", models.TextField(blank=True)),
                ("last_crawled_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("knowledge_base", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="documents", to="ai.knowledgebase")),
            ],
            options={"db_table": "knowledge_documents", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="CoworkerKnowledgeBaseAttachment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("coworker", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="knowledge_base_attachments", to="core.coworker")),
                ("knowledge_base", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="coworker_attachments", to="ai.knowledgebase")),
            ],
            options={"db_table": "coworker_knowledge_base_attachments"},
        ),
        migrations.CreateModel(
            name="KnowledgeChunk",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("chunk_index", models.PositiveIntegerField()),
                ("content", models.TextField()),
                ("embedding", pgvector.django.VectorField(dimensions=1536)),
                ("token_count", models.PositiveIntegerField()),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chunks", to="ai.knowledgedocument")),
            ],
            options={"db_table": "knowledge_chunks"},
        ),
        migrations.AddConstraint(model_name="coworkerknowledgebaseattachment", constraint=models.UniqueConstraint(fields=("coworker", "knowledge_base"), name="uniq_coworker_knowledge_base")),
        migrations.AddConstraint(model_name="knowledgechunk", constraint=models.UniqueConstraint(fields=("document", "chunk_index"), name="uniq_document_chunk")),
        migrations.AddIndex(model_name="memoryentry", index=pgvector.django.HnswIndex(ef_construction=64, fields=["embedding"], m=16, name="memory_entry_embedding_hnsw", opclasses=["vector_cosine_ops"])),
        migrations.AddIndex(model_name="knowledgechunk", index=pgvector.django.HnswIndex(ef_construction=64, fields=["embedding"], m=16, name="knowledge_chunk_embedding_hnsw", opclasses=["vector_cosine_ops"])),
    ]
