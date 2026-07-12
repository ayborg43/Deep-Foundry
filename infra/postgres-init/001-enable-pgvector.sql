-- pgvector/pgvector images ship the extension but don't enable it per-database
-- automatically. Memory/knowledge tables (Milestone 5) depend on this being
-- present from the start, per ARCHITECTURE.md §4.1 / DATABASE.md §3.1-3.2.
CREATE EXTENSION IF NOT EXISTS vector;
