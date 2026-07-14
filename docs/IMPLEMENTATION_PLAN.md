## IMPLEMENTATION_PLAN.md

# Deep-Foundry — MVP Implementation Plan

> Downstream of every other document. Scope is **Phase 1 / MVP** as defined in `ROADMAP.md`. Do not begin implementation until this plan is reviewed and approved — per the original mandate, architecture and planning precede code. Milestones are dependency-ordered; epics within a milestone can generally proceed in parallel once that milestone's foundation lands.

## How to Read This Plan

- **Milestone** = a deployable/demoable increment.
- **Epic** = a body of work within a milestone, scoped to one or two modules from `SOUL.md` §5.
- **User Story** = `As a <role>, I want <capability>, so that <outcome>` — the unit product/eng alignment happens at.
- **Task** = an engineering-sized unit of work under a story, roughly PR-sized.

Every epic references the doc sections it must stay consistent with. No task here should require inventing a decision that contradicts those sections — if it does, stop and flag it rather than proceeding (per `SOUL.md`'s core instruction).

---

## Milestone 0 — Foundation & Scaffolding

**Goal:** A running, empty skeleton of the whole system — the application serves both Core and AI routes from one process, a worker process shares its codebase, CI is green, nothing does anything useful yet.

### Epic 0.1 — Monorepo & Infra Scaffolding
*Refs: `ARCHITECTURE.md` §2–3, §8; `CONTRIBUTING.md` §2*

- **Story:** As a contributor, I want a working local dev environment in one command, so that I can start building without fighting setup.
  - Task: Scaffold monorepo structure (`/apps`, `/services/app` with `/core`, `/ai`, `/worker` subpackages, `/packages`, `/infra`, `/docs`) per `CONTRIBUTING.md` §2.
  - Task: `docker-compose.yml` bringing up Postgres (+pgvector), Redis, MinIO, an `app` container (ASGI, one image), a `worker` container (same image, `celery worker` command), reverse-proxy gateway for local dev — per `ARCHITECTURE.md` §8.1. This is the same Compose file Milestone 8 hardens and verifies against Dokploy for production self-hosting, so keep it Dokploy-compatible from the start rather than diverging into a local-only shape.
  - Task: Base Django project (`services/app/core`) with DRF installed, health-check endpoint.
  - Task: Base FastAPI sub-app (`services/app/ai`) mounted into the Django ASGI app at `/ai/*`; verify both `/health` (core) and `/ai/health` (AI) respond from the same running process.
  - Task: Base Celery app (`services/app/worker`) importing `core`/`ai` directly; a no-op `ping` task runnable via `celery -A app worker` to confirm the worker entrypoint boots against the same codebase.
  - Task: Base Next.js app (`apps/web`) with Tailwind + shadcn/ui wired.
  - Task: GitHub Actions CI: lint + test + build **one** application image (used for both `app` and `worker` roles) on every PR, per `ARCHITECTURE.md` §8.3.

### Epic 0.2 — Core Data Model Bootstrap
*Refs: `DATABASE.md` §2.1*

- **Story:** As a backend engineer, I want the foundational identity/workspace tables migrated, so that every later epic has something to build on.
  - Task: Migrate `users`, `oauth_identities`, `workspaces`, `workspace_members`.
  - Task: Seed/fixture data for local dev.

### Epic 0.3 — Internal Module Interface
*Refs: `API.md` §12; `ARCHITECTURE.md` §3.1*

- **Story:** As a platform engineer, I want the Core↔AI interface defined as an in-process module boundary, so that AI code and worker code never duplicate Core logic, and the seam is ready to become a real service boundary later if that's ever earned.
  - Task: Implement the interface functions from `API.md` §12 (`get_coworker_config`, `get_provider_credential`, `report_task_status`, `create_approval_request`, `write_audit_log`) as a module in `services/app/core` that `ai` and `worker` import — never the other direction.
  - Task: Stub implementations returning fixture data; verify both the ASGI process and a Celery worker process can import and call them successfully in the same test run.

**Exit criteria:** `docker-compose up` produces a running, healthy stack (one `app` container serving Core + AI routes, one `worker` container executing a no-op task against the same codebase); CI passes on an empty-but-structured codebase.

---

## Milestone 1 — Auth, Workspace & Identity

**Goal:** A user can sign up, log in, and land in their personal workspace.

### Epic 1.1 — Authentication
*Refs: `SOUL.md` §5.1, §6.1; `API.md` §2; `SECURITY.md` §2*

- **Story:** As a new user, I want to sign up with email/password or Google OAuth, so that I can start using Deep-Foundry without friction.
  - Task: Registration/login/logout/refresh endpoints (`API.md` §2), Argon2id password hashing (`SECURITY.md` §2).
  - Task: Google OAuth flow (callback handling, identity linking).
  - Task: Session/JWT issuance with refresh-token rotation.
  - Task: Web app: sign-up, login, logout screens.
- **Story:** As a security-conscious user, I want to enable MFA, so that my account is protected.
  - Task: TOTP MFA enrollment + verification endpoint and flow.

### Epic 1.2 — Personal Workspace
*Refs: `SOUL.md` §5.2, §6.1; `DATABASE.md` §2.1*

- **Story:** As a new user, I want a personal workspace created automatically on signup, so that I don't have to configure anything before I can use the product.
  - Task: Auto-provision `type=personal` workspace + owner membership on registration.
  - Task: `GET/PATCH /me`, `GET/PATCH /workspaces/{id}` endpoints.
  - Task: `GET /workspaces` (list, per `API.md` §2) — added during implementation: `/auth/login` and `/auth/mfa/verify` only return tokens, not a workspace, so a client without a fresh register/OAuth response needs a way to discover which workspace(s) it can act in.
  - Task: Web app: workspace settings shell (empty for now, populated by later milestones).

### Epic 1.3 — Provider Credentials
*Refs: `SOUL.md` §5.2; `DATABASE.md` §2.7; `SECURITY.md` §6*

- **Story:** As a user, I want to add my own DeepSeek API key, so that my coworkers can run against my own account rather than a shared platform key.
  - Task: `provider_credentials` table + envelope encryption at rest (`deployment_mode = deepseek_cloud` for MVP; `deepseek_self_hosted` reserved per `DATABASE.md` §2.7).
  - Task: CRUD endpoints (`API.md` §2) — create, list (masked), delete.
  - Task: Web app: Settings → Provider Credentials screen (DeepSeek API key entry for MVP).

**Exit criteria:** A user can register, verify MFA optionally, land in a personal workspace, and add at least one provider API key — all through the UI, no admin/DB access required.

---

## Milestone 2 — Model Router

**Goal:** The AI modules can call DeepSeek's Cloud API through one internal interface, with capability negotiation and fallback across DeepSeek's own model tiers — built against an adapter contract that leaves room for a second (self-hosted) adapter later without a redesign.

### Epic 2.1 — DeepSeek Cloud Adapter
*Refs: `SOUL.md` §16; `ARCHITECTURE.md` §5, ADR-007*

- **Story:** As a platform engineer, I want a deployment-mode adapter contract with one concrete implementation, so that adding self-hosted DeepSeek inference later never touches application code.
  - Task: Define adapter interface (`generate`, `capabilities`, `estimate_cost`, `health_check`) per `ARCHITECTURE.md` §5.
  - Task: Implement the DeepSeek Cloud API adapter — chat (DeepSeek-V3) and reasoning (DeepSeek-R1) model support, tool-calling.
  - Task: Unified request/response normalization layer, including tool-calling schema normalization (kept even with one adapter, so it doesn't need retrofitting when the self-hosted adapter lands).

### Epic 2.2 — Router Logic
*Refs: `SOUL.md` §16.3*

- **Story:** As a coworker execution engine, I want the router to negotiate capabilities and fall back on failure, so that a coworker doesn't break when its primary model is degraded or a request needs escalation.
  - Task: Capability negotiation (reject/degrade if bound model lacks a required capability, e.g. a non-reasoning request routed to a reasoning-only config).
  - Task: Fallback chain execution + logging on adapter failure/rate limit (e.g. DeepSeek-V3 → DeepSeek-R1 escalation, or retry on rate limit).
  - Task: `model_calls` structured logging (`DATABASE.md` §3.4) feeding cost/usage.

### Epic 2.3 — Streaming
*Refs: `API.md` §1, §4*

- **Story:** As a user, I want to see a coworker's response stream in, so that the product feels responsive, not batch.
  - Task: SSE streaming plumbing from the DeepSeek adapter → AI modules → API Gateway → client, all within the one ASGI process for the synchronous chat path.

**Exit criteria:** An internal test harness can send the same prompt through DeepSeek-V3 and DeepSeek-R1 via the router and get normalized, streamed responses with usage logged for both.

---

## Milestone 3 — Coworkers

**Goal:** A user can create, configure, and see a roster of persistent coworkers.

### Epic 3.1 — Coworker CRUD & Versioning
*Refs: `SOUL.md` §4.2, §8; `DATABASE.md` §2.2; `API.md` §3*

- **Story:** As a user, I want to create a coworker with a name, role, and bound model, so that I have a persistent entity to work with instead of a one-off chat.
  - Task: `coworkers` + `coworker_versions` tables and migration.
  - Task: Create/get/update(new version)/archive endpoints.
  - Task: Web app: Coworker creation flow (`UI_GUIDELINES.md` §3.2) — name, role description, model selection.
  - Task: Web app: Coworkers roster page (`UI_GUIDELINES.md` §2).
- **Story:** As a user, I want to see and roll back a coworker's configuration history, so that I can undo a bad change.
  - Task: Version history endpoint + rollback action.
  - Task: Web app: version history panel with diff view.

### Epic 3.2 — Skills, Tools, Knowledge Attachment (structural)
*Refs: `SOUL.md` §4.6–4.8; `DATABASE.md` §2.2*

- **Story:** As a user, I want to attach built-in tools to my coworker, so that it can actually do things beyond talk.
  - Task: `tools` catalog table + seed data for built-in tools (web search, workspace-scoped file read/write, sandboxed code execution).
  - Task: `coworker_tool_attachments` CRUD + endpoints.
  - Task: Web app: attach/detach tools UI in coworker config panel.

*(Full Skill-as-installable-marketplace-object and Knowledge Base ingestion are separate epics below/in Milestone 5 — this epic covers only the structural attachment mechanism both will plug into.)*

**Exit criteria:** A user can create a coworker, bind it to any provider configured in Milestone 1, attach a built-in tool, and see it on their roster.

---

## Milestone 4 — Chat

**Goal:** A user can have a real, streaming, tool-transparent conversation with a coworker.

### Epic 4.1 — Conversations & Messaging
*Refs: `SOUL.md` §5.4, §6.3; `DATABASE.md` §3.3; `API.md` §4*

- **Story:** As a user, I want to start a conversation with a coworker and see it respond in real time, so that interacting feels immediate.
  - Task: `conversations`/`messages` tables + migrations.
  - Task: Send-message endpoint + SSE stream endpoint.
  - Task: Web app: chat UI — message list, streaming render, input box.

### Epic 4.2 — Tool-Call Transparency
*Refs: `SOUL.md` §6.3; `UI_GUIDELINES.md` §3.1*

- **Story:** As a user, I want to see what tools my coworker is calling and why, so that I trust what it's doing.
  - Task: Tool-call event emission on the SSE stream (`tool_call_started`, `tool_call_result`).
  - Task: Web app: inline expandable tool-call cards in the message stream.

### Epic 4.3 — Approval Gate (first pass)
*Refs: `SOUL.md` §15.2; `SECURITY.md` §4; `ARCHITECTURE.md` §6*

- **Story:** As a user, I want to be asked before my coworker does anything risky, so that I stay in control.
  - Task: `permission_profiles`, `tools.risk_classification`, `approval_requests` tables + migrations.
  - Task: Approval-gate enforcement in the Security & Permissions library (hard invariant: `dangerous` never auto-executes, per `SECURITY.md` §4).
  - Task: `approval_required` SSE event + approve/deny endpoints.
  - Task: Web app: inline approval prompt card (`UI_GUIDELINES.md` §3.1).

**Exit criteria:** A user chats with a coworker that has a `dangerous`-classified tool attached; the coworker's attempt to use it correctly blocks and surfaces an inline approval prompt; approving lets it proceed, denying stops it — all logged to `audit_log`.

---

## Milestone 5 — Memory & Knowledge

**Goal:** Coworkers remember things across sessions and can search attached documents.

### Epic 5.1 — Memory System
*Refs: `SOUL.md` §12; `DATABASE.md` §3.2; `API.md` §5*

- **Story:** As a coworker, I want to write and recall facts across sessions, so that I don't ask the same question twice.
  - Task: `memory_entries` table + pgvector embedding column + ANN index.
  - Task: Memory write path (automatic, from conversation summarization) + manual write endpoint.
  - Task: Semantic search function used by the AI modules to ground responses (called in-process, both from live chat and from Celery worker task execution).
  - Task: Web app: memory timeline view + manual edit/delete (`SOUL.md` §12.2).

### Epic 5.2 — Knowledge Base Ingestion
*Refs: `SOUL.md` §4.8, §6.4; `DATABASE.md` §3.1; `API.md` §5*

- **Story:** As a user, I want to upload a document and have my coworker be able to answer questions about it, so that it's grounded in my actual material, not just training data.
  - Task: `knowledge_bases`/`knowledge_documents`/`knowledge_chunks` tables + migrations.
  - Task: Upload endpoint → MinIO storage → async Celery ingestion job (chunk → embed → store).
  - Task: Retrieval integration into the chat/coworker execution path (RAG).
  - Task: Web app: knowledge base creation + document upload + ingestion status UI.

**Exit criteria:** A user uploads a PDF, attaches it to a coworker, asks a question only answerable from that document, and gets a grounded answer with the relevant memory/knowledge visibly used.

---

## Milestone 6 — Background Execution & Task Engine

**Goal:** A coworker can work on something without a human watching the whole time.

### Epic 6.1 — Task Engine
*Refs: `SOUL.md` §5.15, §6.2; `DATABASE.md` §2.6; `API.md` §6*

- **Story:** As a user, I want to hand a coworker a task and check back later, so that I'm not blocked babysitting a conversation.
  - Task: `tasks` table + migration.
  - Task: Task creation (from chat handoff or direct API), Celery execution job.
  - Task: Task status lifecycle (`pending → in_progress → needs_approval/blocked → completed/failed`).
  - Task: Web app: task list/detail view, approval inbox (`UI_GUIDELINES.md` §3.3).

### Epic 6.2 — Notifications
*Refs: `SOUL.md` §5.10, §4.20; `DATABASE.md` §2.8*

- **Story:** As a user, I want to be notified when a task needs my approval or finishes, so that I don't have to keep checking manually.
  - Task: `notifications` table + in-app notification bell.
  - Task: Email notification dispatch for approval-required and task-complete events.

**Exit criteria:** A user assigns a coworker a multi-step task involving a `dangerous` tool, closes the tab, gets an email when approval is needed, approves from the notification, and later sees the completed result.

---

## Milestone 7 — Observability, Audit & Cost

**Goal:** Every action a coworker takes is visible, attributable, and costed.

### Epic 7.1 — Audit Log
*Refs: `SOUL.md` §15.2, §6.11; `DATABASE.md` §2.3; `SECURITY.md` §8*

- **Story:** As a workspace owner, I want an immutable record of everything my coworkers did, so that I can review and trust the system.
  - Task: `audit_log` append-only table, `POST /internal/v1/audit-log` write path used by both services.
  - Task: `GET /workspaces/{ws}/audit-log` endpoint + web app audit viewer.

### Epic 7.2 — Cost & Usage Dashboard
*Refs: `SOUL.md` §6.11, §16.3; `DATABASE.md` §2.7, §3.4*

- **Story:** As a user, I want to see what my coworkers are costing me, per coworker and per provider, so that I can manage spend.
  - Task: `usage_records` rollup from `model_calls` stream.
  - Task: Cost dashboard endpoint + web app view (`SOUL.md` §6.11).

**Exit criteria:** A workspace owner can see, for the last 30 days, total cost broken down by coworker and provider, and can pull up the full audit trail for any single coworker action.

---

## Milestone 8 — Self-Hosted Packaging & Launch Readiness

**Goal:** Anyone can self-host the MVP following documentation alone.

### Epic 8.1 — Deployment Hardening
*Refs: `ARCHITECTURE.md` §8.1; `SECURITY.md` §11*

- **Story:** As an operator, I want a documented, secure Dokploy deployment, so that I can self-host without a core-team engineer's help.
  - Task: Production-ready `docker-compose.yml` verified deployable through Dokploy (secrets via env, backup guidance) — per `ARCHITECTURE.md` §8.1/ADR-008.
  - Task: Point the Postgres service at a pgvector-enabled image (`pgvector/pgvector:pg16`) rather than Dokploy's default Postgres, per `ARCHITECTURE.md` §8.1's operator note.
  - Task: Setup documentation (README-level: Dokploy install → app deploy → first-run) referencing `ARCHITECTURE.md` §8.1 and `SECURITY.md` §11 operator responsibilities; document the raw-`docker-compose`-without-Dokploy fallback path too.
  - Task: Master-key/secrets bootstrap flow for first-run setup.

### Epic 8.2 — End-to-End Hardening Pass
*Refs: all documents*

- **Story:** As the project, I want the full MVP feature set exercised end-to-end with adversarial security test cases, so that launch doesn't ship a broken trust guarantee.
  - Task: Adversarial test suite: prove `dangerous` tools cannot execute without approval under any coworker/org config combination (`SECURITY.md` §4, `CONTRIBUTING.md` §7).
  - Task: Full doc-consistency pass — verify no drift between `SOUL.md` and the implemented system; update docs where reality has legitimately evolved, per the revision process in `CONTRIBUTING.md` §5 if a principle itself needs to change.
  - Task: Accessibility pass against `UI_GUIDELINES.md` §5 (WCAG 2.1 AA) on Chat and Approval Queue specifically.

**Exit criteria — this is the MVP exit criteria from `ROADMAP.md`:** A single user can self-host the stack, create a coworker, bind it to DeepSeek's Cloud API, have it remember facts across sessions, attach a document as knowledge, and have a `dangerous` tool call correctly blocked pending their approval — all without touching a database directly or reading source code.

---

## Sequencing Summary

```
M0 Foundation
  └─ M1 Auth/Workspace ──┐
                          ├─ M2 Model Router ──┐
                          │                     ├─ M3 Coworkers ──┐
                          │                     │                  ├─ M4 Chat ──┐
                          │                     │                  │             ├─ M5 Memory/Knowledge ─┐
                          │                     │                  │             │                        ├─ M6 Task Engine ─┐
                          │                     │                  │             │                        │                    ├─ M7 Observability ─┐
                          │                     │                  │             │                        │                    │                     └─ M8 Launch Readiness
```

M2 (Model Router) can proceed in parallel with M1's later tasks once M0 is done, since it has no dependency on auth beyond the internal service contract. M4's Approval Gate epic (4.3) is the first point where `SECURITY.md`'s core invariant becomes real and testable — treat it as the milestone's critical path item, not a nice-to-have appended at the end.

## Completion Status

Phase 1 Milestones 0–8 are implemented. The maintained release acceptance steps
are in `SELF_HOSTING.md`; future implementation work proceeds from Phase 2 in
`ROADMAP.md`.

Phase 2 and Phase 3 are now implemented. Detailed acceptance paths and operator
configuration are maintained in `PHASE2_IMPLEMENTATION.md` and
`PHASE3_IMPLEMENTATION.md`.

Phase 4 is implemented from the former research track. Its concrete scope,
acceptance paths, provider limitations, and security invariants are maintained in
`PHASE4_IMPLEMENTATION.md`.
