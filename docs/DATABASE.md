## DATABASE.md

# Agentarium — Database Design

> Downstream of `SOUL.md` ([Section 4, Core Concepts](SOUL.md#4-core-concepts)) and `ARCHITECTURE.md` ([Section 4, Data Layer](ARCHITECTURE.md#4-data-layer)). Schema names below are illustrative (`snake_case` table names, `id` as UUID primary key convention) — exact migration syntax belongs in the codebase, not this document. This document is the contract that migrations must satisfy, not a replacement for them.

## 1. Conventions

- All primary keys are UUIDv7 (time-ordered, sortable, no central sequence bottleneck) unless noted.
- All tables carry `created_at`, `updated_at` timestamps; soft-deletable tables additionally carry `deleted_at` (nullable) rather than hard deletes, so audit history and marketplace provenance survive removal.
- Foreign keys are named `<referenced_table_singular>_id`.
- JSON/JSONB columns are used only for genuinely schemaless, self-describing content (tool call payloads, manifest metadata) — never as a substitute for a proper relation.
- Two logical schemas per `ARCHITECTURE.md` §4.1: `core` (owned by the Core modules) and `ai` (owned by the AI modules), physically one Postgres instance accessed from one application process for MVP per `ARCHITECTURE.md` ADR-006.

---

## 2. Schema: `core`

### 2.1 Identity & Workspace

**`users`**
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| email | text unique | |
| password_hash | text nullable | null if OAuth-only |
| display_name | text | |
| avatar_url | text nullable | |
| mfa_enabled | boolean default false | |
| created_at / updated_at | timestamptz | |

**`oauth_identities`** — `id, user_id FK, provider (enum: google/github/microsoft/saml), provider_user_id, created_at`

**`workspaces`**
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| name | text | |
| type | enum(`personal`,`organization`) | |
| owner_user_id | uuid FK → users | |
| plan_tier | enum(`self_hosted_free`,`cloud_free`,`cloud_pro`,`cloud_enterprise`) | |
| created_at / updated_at | | |

**`workspace_members`** — `id, workspace_id FK, user_id FK, role (enum: owner/admin/member/guest), invited_by uuid FK users nullable, joined_at`

**`teams`** *(human teams, distinct from Agent Teams — see 2.4)* — `id, workspace_id FK, name, created_at`

**`team_members`** — `id, team_id FK, user_id FK, role`

### 2.2 Coworkers & Configuration

**`coworkers`**
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| workspace_id | uuid FK → workspaces | |
| owner_type | enum(`user`,`team`,`organization`) | supports [SOUL.md §8](SOUL.md#8-coworker-features) shared/org coworkers |
| owner_id | uuid | polymorphic ref to user_id or team_id |
| name | text | |
| avatar_url | text nullable | |
| role_description | text | the "job description" / system instructions |
| current_version_id | uuid FK → coworker_versions | points at the active config version |
| status | enum(`active`,`archived`) | |
| created_at / updated_at | | |

**`coworker_versions`** — `id, coworker_id FK, version_number int, role_description text, model_binding jsonb (primary model + fallback chain), permission_profile_id FK, created_by uuid FK users, created_at, changelog text nullable` — implements [SOUL.md Development Rule 8](SOUL.md#20-development-rules) versioning for coworkers.

**`coworker_skill_attachments`** — `id, coworker_id FK, skill_id FK → skill_versions, enabled boolean, attached_at`

**`coworker_tool_attachments`** — `id, coworker_id FK, tool_id FK, config jsonb (tool-specific settings), enabled boolean`

**`coworker_knowledge_attachments`** — `id, coworker_id FK, knowledge_base_id FK, access_level enum(read,read_write)`

**`coworker_analytics_daily`** *(rollup table for performance dashboards)* — `id, coworker_id FK, date, tasks_completed, tasks_failed, approval_requests, approval_denials, total_cost_usd, avg_response_seconds`

### 2.3 Permissions

**`permission_profiles`** — `id, workspace_id FK nullable (null = platform default), name, default_tool_risk_policy jsonb ({safe: auto, sensitive: auto|approval, dangerous: approval — dangerous can never be set to auto, enforced at application layer per SOUL.md §15.2}), created_at`

**`tools`** *(platform-wide catalog, not workspace-scoped)* — `id, name, description, risk_classification enum(safe,sensitive,dangerous), input_schema jsonb, output_schema jsonb, provider enum(built_in, skill_bundled, integration), created_at`

**`org_policy_floors`** — `id, workspace_id FK, tool_risk_classification enum, min_required_policy enum(approval), enforced boolean default true` — implements the "org policy floor that coworker config cannot loosen" guarantee from [SOUL.md §15.2](SOUL.md#152-the-permission--approval-system).

**`approval_requests`** — `id, task_id FK nullable, workflow_run_step_id FK nullable, coworker_id FK, tool_id FK, requested_action jsonb, status enum(pending,approved,denied,expired), decided_by uuid FK users nullable, decided_at timestamptz nullable, created_at`

**`audit_log`** *(append-only, immutable — no update/delete path in application code)* — `id, workspace_id FK, actor_type enum(user,coworker,system), actor_id uuid, action text, resource_type text, resource_id uuid, metadata jsonb, created_at` — indexed on `(workspace_id, created_at)` for admin audit views per [SOUL.md §5.8](SOUL.md#58-admin).

### 2.4 Agent Teams & Projects

**`agent_teams`** — `id, workspace_id FK, name, collaboration_pattern enum(sequential,manager_delegate,parallel_merge), current_version_id FK, created_at`

**`agent_team_versions`** — `id, agent_team_id FK, version_number, created_by, created_at`

**`agent_team_members`** — `id, agent_team_version_id FK, coworker_id FK, role enum(manager,researcher,writer,reviewer,developer,tester,security_reviewer,architect,planner,product_manager,custom), custom_role_label text nullable`

**`projects`** — `id, workspace_id FK, name, description, status enum(active,archived), created_at`

**`project_resources`** *(polymorphic association)* — `id, project_id FK, resource_type enum(conversation,task,knowledge_base,coworker,agent_team), resource_id uuid, added_at`

### 2.5 Marketplace

**`marketplace_listings`** — `id, listing_type enum(skill,capability_pack,workflow_template,tool), publisher_workspace_id FK, visibility enum(public,unlisted,org_private), pricing_model enum(free,paid,pay_what_you_want), price_usd numeric nullable, verified_publisher boolean default false, created_at`

**`marketplace_listing_versions`** — `id, listing_id FK, version_string text (semver), manifest jsonb, changelog text, review_status enum(pending,approved,rejected), reviewed_at timestamptz nullable, published_at timestamptz`

**`skill_versions`** — `id, listing_version_id FK → marketplace_listing_versions, instruction_content text, declared_tools jsonb (tool ids + risk classes), dependencies jsonb (skill/tool ids)`

**`marketplace_installs`** — `id, workspace_id FK, listing_version_id FK, installed_by uuid FK users, forked_from_listing_version_id FK nullable (provenance per SOUL.md §10.4), installed_at`

**`marketplace_reviews`** — `id, listing_id FK, workspace_id FK, user_id FK, rating int (1-5), review_text text nullable, created_at`

### 2.6 Workflows & Tasks

**`workflows`** — `id, workspace_id FK, name, current_version_id FK, marketplace_listing_id FK nullable (if published), created_at`

**`workflow_versions`** — `id, workflow_id FK, version_number, definition jsonb (steps, branches, checkpoints), created_by, created_at`

**`workflow_triggers`** — `id, workflow_id FK, trigger_type enum(manual,scheduled,event), schedule_cron text nullable, event_source text nullable, enabled boolean`

**`workflow_runs`** — `id, workflow_version_id FK, triggered_by enum(user,schedule,event), status enum(running,needs_approval,completed,failed,cancelled), current_step_index int, started_at, completed_at nullable`

**`workflow_run_steps`** — `id, workflow_run_id FK, step_index int, step_type enum(coworker_action,tool_call,human_checkpoint), status enum(pending,in_progress,needs_approval,completed,failed,skipped), result jsonb nullable, started_at, completed_at nullable`

**`tasks`** — `id, workspace_id FK, project_id FK nullable, coworker_id FK (assignee), created_by_type enum(user,coworker,workflow), created_by_id uuid, title, description, status enum(pending,in_progress,needs_approval,blocked,completed,failed), due_at timestamptz nullable, parent_task_id uuid FK nullable (delegation from a Manager coworker per SOUL.md §9.2), created_at, completed_at nullable`

### 2.7 Billing

**`provider_credentials`** — `id, workspace_id FK, deployment_mode enum(deepseek_cloud, deepseek_self_hosted), encrypted_key bytea nullable (the DeepSeek Cloud API key; null for deepseek_self_hosted), endpoint_url text nullable (the self-hosted inference endpoint; null for deepseek_cloud), label text, is_default boolean, created_at` — `deepseek_self_hosted` is a reserved value for the self-hosted DeepSeek inference adapter planned per [SOUL.md §16.2](SOUL.md#162-supported-deployment-modes); only `deepseek_cloud` is writable/usable in the MVP application layer until that adapter ships.

**`usage_records`** — `id, workspace_id FK, coworker_id FK nullable, deployment_mode, model_id, input_tokens, output_tokens, cost_usd, request_id uuid, recorded_at` — feeds cost dashboards per [SOUL.md §6.11](SOUL.md#611-observability--trust); same event stream backs both billing and audit per [ARCHITECTURE.md §9](ARCHITECTURE.md#9-observability-architecture).

**`subscriptions`** — `id, workspace_id FK, plan_tier, seats int nullable, status enum(active,past_due,cancelled), renews_at`

**`marketplace_payouts`** — `id, publisher_workspace_id FK, listing_id FK, period_start, period_end, gross_usd, platform_fee_usd, net_payout_usd, status enum(pending,paid)`

### 2.8 Notifications

**`notifications`** — `id, workspace_id FK, user_id FK, type enum(task_completed,approval_requested,workflow_failed,mention,billing), payload jsonb, read_at timestamptz nullable, created_at`

---

## 3. Schema: `ai`

### 3.1 Knowledge

**`knowledge_bases`** — `id, workspace_id FK (references core.workspaces, cross-schema logical FK), scope enum(coworker,project,workspace), scope_id uuid, name, source_type enum(document,url,spreadsheet,database,conversation), created_at`

**`knowledge_documents`** — `id, knowledge_base_id FK, source_uri text, mime_type, object_storage_key text (MinIO/S3 path), ingestion_status enum(pending,chunking,embedding,ready,failed), last_crawled_at timestamptz nullable, created_at`

**`knowledge_chunks`** — `id, document_id FK, chunk_index int, content text, embedding vector(1536) (pgvector column, dimension per embedding model in use), token_count int`
- Index: `ivfflat` or `hnsw` index on `embedding` for approximate nearest-neighbor search.

### 3.2 Memory

**`memory_entries`**
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| scope | enum(`user`,`coworker`,`project`,`organization`,`temporary`) | per [SOUL.md §12.1](SOUL.md#121-scopes) |
| scope_id | uuid | polymorphic ref |
| workspace_id | uuid | for tenant-scoped queries regardless of memory scope |
| content | text | |
| embedding | vector(1536) | for semantic search |
| source_type | enum(`conversation`,`task_result`,`manual`,`workflow_run`) | powers the memory timeline per [SOUL.md §12.2](SOUL.md#122-mechanics) |
| source_ref_id | uuid nullable | e.g. the conversation/message id it originated from |
| is_long_term | boolean default false | temporary memory not yet promoted has this false |
| promoted_at | timestamptz nullable | |
| created_at / updated_at | | |

**`memory_access_grants`** — `id, memory_scope, memory_scope_id, grantee_type enum(coworker,team,user), grantee_id uuid, access_level enum(read,read_write), granted_by uuid FK users, granted_at` — implements explicit cross-coworker memory sharing per [SOUL.md §12.2](SOUL.md#122-mechanics).

### 3.3 Chat

**`conversations`** — `id, workspace_id, project_id nullable, created_by uuid FK users, title, created_at`

**`conversation_participants`** — `id, conversation_id FK, participant_type enum(user,coworker), participant_id uuid`

**`messages`** — `id, conversation_id FK, sender_type enum(user,coworker,system), sender_id uuid nullable, content text, tool_calls jsonb nullable (rendered inline per SOUL.md §6.3), parent_message_id uuid nullable (branching/regeneration), created_at`

### 3.4 Model Router / Execution Logs

**`model_calls`** — `id, request_id uuid, workspace_id, coworker_id nullable, deployment_mode, model_id, capability_requested jsonb, fallback_used boolean, latency_ms int, status enum(success,error,rate_limited), created_at` — the structured event referenced in [ARCHITECTURE.md §9](ARCHITECTURE.md#9-observability-architecture); `usage_records` in `core` is derived from this stream during a nightly/streaming rollup, not independently recorded.

**`tool_call_logs`** — `id, request_id uuid, task_id nullable, coworker_id, tool_id, input jsonb, output jsonb, sandbox_container_id text nullable, status enum(success,error,denied), created_at`

---

## 4. Cross-Schema Relationship Notes

- `ai.knowledge_bases.workspace_id`, `ai.memory_entries.workspace_id`, and `ai.model_calls.workspace_id` are **logical** foreign keys to `core.workspaces.id` — enforced at the application layer (the AI modules validate workspace existence via the in-process Core↔AI interface documented in [API.md §12](API.md#12-internal-module-interface--core--ai), a normal Python call for MVP since both run in the same process per [ARCHITECTURE.md ADR-006](ARCHITECTURE.md#11-architecture-decision-records-initial-set)), not a physical cross-schema FK constraint, since the two schemas are architected to be splittable into physically separate databases later without a migration of referential integrity logic — independent of whether the application process itself is ever split.
- `core.coworker_versions.permission_profile_id` and `core.org_policy_floors` are evaluated together by the Security & Permissions library at execution time (called identically from Core modules, AI modules, and Celery workers, per [ARCHITECTURE.md §7](ARCHITECTURE.md#7-security-boundary-placement)) — the *effective* permission for a given tool call is `max(strictness)` of the coworker's own profile and any applicable org policy floor, computed at call time, not pre-materialized into a single column (so an org tightening its floor retroactively applies to every existing coworker without a data migration).

---

## 5. Indexing Priorities (MVP)

| Table | Index | Reason |
|---|---|---|
| `messages` | `(conversation_id, created_at)` | chat history pagination |
| `memory_entries` | `embedding` (ivfflat/hnsw) + `(scope, scope_id)` | semantic search scoped to the right memory pool |
| `knowledge_chunks` | `embedding` (ivfflat/hnsw) | RAG retrieval |
| `audit_log` | `(workspace_id, created_at)` | admin audit view pagination |
| `tasks` | `(workspace_id, status)` | task queue/dashboard views |
| `usage_records` | `(workspace_id, recorded_at)` | cost dashboard aggregation |
| `approval_requests` | `(coworker_id, status)` | approval inbox |

---

## 6. Data Retention & Deletion

- Soft-delete (`deleted_at`) on all user-owned content tables; hard deletion is a background job run only after a workspace's configured retention window (default 30 days) to support undo, consistent with [SOUL.md §1.6](SOUL.md#16-design-principles) ("reversibility over restriction").
- `audit_log` is append-only and exempt from soft-delete entirely — it is retained per workspace compliance settings and is the one table where deletion is a compliance/legal action, not a user action.
- Memory and knowledge deletion cascades are explicit and user-visible (per [SOUL.md §12.2](SOUL.md#122-mechanics), memory is "never a black box") — deleting a Knowledge Base prompts confirmation naming every coworker currently attached to it.
