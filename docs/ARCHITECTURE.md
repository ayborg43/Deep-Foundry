## ARCHITECTURE.md

# Agentarium — Technical Architecture

> Downstream of `SOUL.md`. Every decision here exists to serve the principles and modules defined there — most directly [Section 5 (Product Modules)](SOUL.md#5-product-modules), [Section 16 (Model Router)](SOUL.md#16-model-router), and [Section 17 (Technical Architecture summary)](SOUL.md#17-technical-architecture). If this document and `SOUL.md` ever disagree, `SOUL.md` wins and this document is wrong until fixed.

---

## 1. Architecture Goals

1. **One code path to DeepSeek, structurally enforced.** The Model Router is not a convention that application code is trusted to follow — it is the *only* code path to DeepSeek's API. This is enforced by module boundaries and interface discipline, not code review alone, and it's what makes adding a self-hosted DeepSeek inference mode later (`SOUL.md` §16.2) a contained addition rather than a hunt through the codebase for direct API calls.
2. **One codebase, two deployment targets.** Self-hosted (Dokploy-managed Docker Compose, single node or Swarm) and cloud (Kubernetes/managed) run the same images with different orchestration, never a forked feature set.
3. **Modular monolith first, service split only when earned.** The core modules (auth, workspaces, billing, marketplace) and the AI modules (model calls, embeddings, agent execution) have different scaling and reliability characteristics, but that difference doesn't justify operating two independently deployed HTTP services before real load proves it necessary — especially for a single-node self-hosted deployment. Agentarium ships as one modular monolith with a hard internal module boundary between the two domains (separate Django apps and a mounted FastAPI ASGI sub-app, enforced by code organization and a documented interface, not a network call), so extracting the AI layer into its own service later — if it's ever earned — is a deployment change against an existing contract, not a rewrite of business logic (see ADR-006).
4. **Permissions are centralized, not scattered.** Every module that performs an action a coworker could take routes through one Security & Permissions evaluation point — never a locally reinvented check.
5. **Everything async-capable is queue-backed.** Background Tasks, Workflow runs, and knowledge ingestion never block a request/response cycle. This is the one process boundary that *is* real and separate from day one — see Celery Workers below — independent of whether Core and AI code share a process.

---

## 2. System Context Diagram (textual)

```
                                   ┌─────────────────────────┐
                                   │        End Users        │
                                   │ (Web browser / Desktop) │
                                   └────────────┬─────────────┘
                                                │ HTTPS
                     ┌──────────────────────────┴──────────────────────────┐
                     │                    API Gateway                       │
                     │  (auth verification, routing, rate limiting,        │
                     │   request/response versioning, webhook ingress)     │
                     └────────────────────────┬──────────────────────────┘
                                                │
                              ┌──────────────────▼────────────────────┐
                              │   Application — modular monolith        │
                              │   one ASGI process (Django + mounted    │
                              │   FastAPI sub-app), one image           │
                              │  ┌──────────────────────────────────┐  │
                              │  │  Core modules (Django apps)        │  │
                              │  │  - Auth · Workspace/Org/Teams      │  │
                              │  │  - Coworkers (config/metadata)     │  │
                              │  │  - Projects · Marketplace          │  │
                              │  │  - Billing · Admin/Audit           │  │
                              │  └──────────────────────────────────┘  │
                              │  ┌──────────────────────────────────┐  │
                              │  │  AI modules (FastAPI, mounted      │  │
                              │  │  at /ai/* in the same process)     │  │
                              │  │  - Model Router                     │  │
                              │  │  - Memory & Embeddings              │  │
                              │  │  - Task/Workflow orchestration      │  │
                              │  │    (enqueue only — execution runs   │  │
                              │  │    in Celery workers, below)        │  │
                              │  └──────────────────────────────────┘  │
                              │   Core ↔ AI calls are in-process Python │
                              │   calls across a documented interface   │
                              │   (API.md §12), never a network hop     │
                              └────────────────┬─────────────────────────┘
                                                │
                    ┌───────────▼──────────┐        ┌─────────────▼─────────────┐
                    │   PostgreSQL          │        │   Redis (broker + cache)   │
                    │   (+ pgvector)        │        │                            │
                    └───────────┬──────────┘        └─────────────┬─────────────┘
                                │                                 │
                    ┌───────────▼──────────┐        ┌─────────────▼─────────────┐
                    │   MinIO (object store) │        │   Celery Workers            │
                    │   (uploads, exports)   │        │   separate process, SAME    │
                    └────────────────────────┘        │   image/codebase — imports  │
                                                        │   Core + AI modules directly │
                                                        └─────────────┬─────────────┘
                                                                      │
                                                        ┌─────────────▼─────────────┐
                                                        │   DeepSeek Cloud API         │
                                                        │   (active — MVP)             │
                                                        │   [self-hosted DeepSeek       │
                                                        │    inference — planned V2]    │
                                                        └────────────────────────────┘

              ┌───────────────────────────┐
              │   Desktop Companion (Tauri) │──── talks only to API Gateway, never
              │   local FS / terminal /     │     directly to the application or workers
              │   clipboard / browser       │
              └───────────────────────────┘
```

The Model Router (and the rest of the AI modules) is invoked from **two contexts**: synchronously, in-process, from the ASGI application when a live chat request needs a streamed response; and from a Celery worker when a Task or Workflow step executes in the background. Both contexts run the exact same Python code — the worker entrypoint imports the AI modules directly rather than calling them over a network, so there is exactly one implementation of "call a model," not two.

---

## 3. Application Breakdown

### 3.1 Application (modular monolith — Django + mounted FastAPI)

One ASGI process, one container image, internally organized into two module groups with a hard boundary between them:

**Core modules (Django apps):**
**Own:** Authentication, Workspace/Organization/Team membership, Coworker *configuration* (the metadata record — role, name, attached skill/tool/knowledge references, permission profile), Projects, Marketplace (listings, installs, ratings), Billing, Admin/Audit surfaces.

**Why Django here:** these domains are relationally modeled, permission-heavy, and benefit from DRF's mature serialization/permission/viewset conventions and Django's admin tooling for internal ops — exactly the "boring CRUD with serious permission requirements" case described in `SOUL.md` §18.

**Does NOT own:** any direct model provider call, any embedding computation, any long-running agent execution. It creates Task/Workflow *records* and hands execution to the AI modules via the documented in-process interface (see `API.md` §12) — it never calls a model provider SDK itself, and never imports an AI module's internals except through that interface.

**AI modules (FastAPI, mounted as an ASGI sub-application at `/ai/*`):**
**Own:** The Model Router (the DeepSeek Cloud adapter today, the planned self-hosted DeepSeek adapter later — `SOUL.md` §16.2), Memory read/write/search, Knowledge ingestion and embedding, the Task Engine's and Workflow Engine's orchestration logic (creating and tracking runs — the actual step *execution* happens in Celery workers, per §3.2).

**Why FastAPI here, mounted rather than standalone:** async-native and Python-first (matching the provider SDK and embedding-library ecosystem), suited to streaming responses without the overhead of adapting a synchronous view — but there's no reason that async sub-application needs its own deployment lifecycle before real load demands it. Mounting it inside the same ASGI process Django serves (via Starlette-style `Mount`, or an equivalent ASGI composition) gets the async/streaming benefit without paying for a second service, a second image, and a second deploy pipeline on day one.

**Talks to:** PostgreSQL/pgvector directly for memory and knowledge data it owns; Redis/Celery to enqueue background execution; the Core modules' data and permission profiles through the documented in-process interface (`API.md` §12) — never importing Core internals directly, so the seam stays real even though it's not a network boundary yet.

### 3.2 Celery Workers (separate process, same codebase)

Execute: Task Engine step runs, Workflow Engine step runs, knowledge ingestion (chunk → embed → store), scheduled workflow trigger evaluation, notification dispatch. Deployed as their own container (same image as the Application, different entrypoint command — `celery -A app worker` instead of the ASGI server), so they scale independently by queue depth without needing a second codebase or a second build. Workers import the Core and AI modules directly, in-process, exactly as the Application does — there is one Python package, run two ways. All jobs are idempotent-by-design (safe to retry) and carry a correlation ID back to the originating Task/Workflow run for Observability.

### 3.3 API Gateway

A thin routing/auth-verification layer in front of the Application (a reverse proxy with auth middleware rather than a bespoke service). For self-hosted deployments this is **Dokploy's built-in Traefik instance** (§8.1) — TLS termination and Let's Encrypt certificate management come from the platform, so there's no separately configured Nginx/Traefik to maintain. The cloud/Kubernetes target uses its own ingress controller instead, per §8.2. Application-level responsibilities beyond raw TLS/routing (JWT/session verification, rate limiting, routing to the Application's Core `/api/v1/...` vs. AI `/api/v1/ai/...` route groups, webhook ingress for external integrations, API versioning) are handled by the shared auth-verification library in front of the Application regardless of which reverse proxy sits in front of it. Because Core and AI share one process, the routing job here is simpler than in a split-service topology — routing to one backend, not choosing between two.

### 3.4 Desktop Companion (Tauri)

A native app that never talks to PostgreSQL, Redis, or the Application/Workers directly — it authenticates like any other client and talks exclusively to the API Gateway over HTTPS (or to a local loopback bridge for capabilities that are purely local, like clipboard access, which never need to leave the machine at all). This keeps the trust boundary identical regardless of client type: the API Gateway and the Security & Permissions evaluation point are the only places that decide what's allowed.

---

## 4. Data Layer

### 4.1 PostgreSQL (+ pgvector)
Single primary relational database for MVP, logically partitioned by schema/module boundary (`core`, `ai`) even though physically one instance and accessed from one process — this keeps the door open to physical separation later without a data-model rewrite, independent of whether the application itself is later split. pgvector extension handles embedding storage/search for Memory and Knowledge Bases, avoiding a separate vector database operational burden until scale specifically demands it (see §10, Scaling Considerations).

### 4.2 Redis
Serves two roles: Celery broker (task/workflow queue) and general-purpose cache (session data, rate-limit counters, hot-path lookups like coworker permission profiles).

### 4.3 MinIO (S3-compatible object storage)
Stores uploaded knowledge source documents, generated artifacts (presentations, diagrams, exports), and Desktop Companion file transfer staging. Self-hostable, with a straightforward swap to managed S3 for the cloud deployment target via the same S3-compatible API — no code branching between deployment targets.

---

## 5. Model Router — Architectural Detail

Expands on `SOUL.md` §16.

```
Coworker/Skill/Workflow execution
  (called in-process from the ASGI app for live chat,
   or from a Celery worker for background task/workflow steps)
              │
              ▼
   ┌────────────────────┐
   │   Model Router API   │   ← single internal interface,
   │  (an AI module)       │      normalized request/response schema
   └──────────┬───────────┘
              │
   ┌──────────┴─────────────────────────────────┐
   │        Deployment-Mode Adapter Interface      │
   │  normalize(request) → DeepSeek call → normalize(response) │
   └───┬─────────────────────────────┬─────────────┘
       │                             │
   DeepSeek Cloud API          Self-Hosted DeepSeek
   Adapter (active — MVP)      Inference Adapter
                                (planned — V2, e.g. vLLM/
                                 Ollama-style local serving)
```

**Adapter contract (every deployment-mode adapter implements — currently one, DeepSeek Cloud; the self-hosted adapter implements the identical contract when it's built):**
- `generate(messages, tools, model_config) -> normalized_response | stream`
- `capabilities(model_id) -> {tool_calling, max_context, reasoning_mode, streaming}`
- `estimate_cost(usage) -> cost`
- `health_check() -> status`

**Cross-cutting Router responsibilities (not adapter-specific):** capability negotiation before dispatch (reject/degrade gracefully if a coworker's configured model can't support a requested capability), fallback chain execution on adapter failure/rate-limit (e.g. DeepSeek-V3 → DeepSeek-R1 escalation, or retry on rate limit), per-call usage logging to the Observability module, tool-calling schema normalization so a Skill's tool definitions don't need to know which DeepSeek deployment mode is serving them.

**Adding the self-hosted adapter** (the one deployment-mode addition currently planned) is scoped to: one new adapter module implementing the contract above, plus a credential/endpoint-schema entry in Workspace settings. It never requires touching Coworker, Skill, Chat, or Workflow code, and never requires touching the Core modules at all — this is the concrete mechanism, not just the policy, behind principle 7, "built on open models, deployment-agnostic" (`SOUL.md` §3).

---

## 6. Task & Workflow Execution Architecture

- A **Task** is the atomic execution record: one coworker, one objective, a status lifecycle, and a result. Created either directly (chat handoff to background, human assignment) or as a step spawned by a **Workflow** run.
- A **Workflow run** is a durable state machine instance: current step, step history, pending human checkpoint (if any), and the triggering event.
- Both are Celery-task-backed: a Core or AI module (whichever originates the request — chat handoff vs. workflow trigger) creates the record via a normal in-process call and enqueues a job; a Celery worker picks it up and invokes the same AI module code — imported directly, not called over HTTP — to run the Model Router and any Tools, then writes status/results back through the same in-process interface.
- **Approval gates are implemented as a first-class step type**, not a side effect — a Task/Workflow step that requires approval transitions to a `needs_approval` status, blocks progression, and emits a Notification; it resumes only via an explicit approval action, logged with the approving user's identity.

---

## 7. Security Boundary Placement

(Full policy detail in `SECURITY.md`; this section places the *architectural* enforcement points.)

- **Authentication:** enforced at the API Gateway — no request reaches the Application unauthenticated.
- **Authorization (RBAC + permission profiles):** evaluated by a shared Security & Permissions library called from every execution context — the Application's Core modules, its AI modules, and the Celery worker entrypoint alike — at the point of action, not just at the gateway, since a valid authenticated session doesn't imply authorization for a specific coworker/tool/workspace resource. Because all three contexts run the same codebase, this is one library called three ways, not three separately-implemented checks.
- **Tool execution sandboxing:** every Tool invocation that executes code or shell commands runs inside an isolated container/microVM, provisioned per call — whether the call originates synchronously from a live chat request in the ASGI process or asynchronously from a Celery-executed Task/Workflow step — with network egress locked to an explicit allowlist per tool, torn down immediately after.
- **Secrets:** provider API keys and integration OAuth tokens live in an encrypted secrets store (envelope-encrypted at rest in PostgreSQL for MVP; a dedicated secrets manager such as Vault is a V2+ upgrade path for cloud/enterprise), decrypted transiently by the AI modules at call time — whether invoked in-process during a live chat request or by a Celery worker — and never logged or returned to the client.

---

## 8. Deployment Architecture

### 8.1 Self-hosted (Dokploy)

**Dokploy** is the recommended self-hosted deployment path: an open-source, self-hostable PaaS that deploys a Docker Compose stack directly, with Traefik and Let's Encrypt TLS built in. The same `docker-compose.yml` bringing up the **application** container (ASGI process serving Core + mounted AI modules), a **worker** container (same image, `celery worker` entrypoint), PostgreSQL, Redis, and MinIO is what Dokploy deploys — Dokploy replaces the manually-configured reverse-proxy gateway from `ARCHITECTURE.md` §3.3 with its bundled Traefik instance, so there's one fewer piece for a self-hosting operator to configure by hand. Two application-role containers instead of three (per the modular-monolith decision, ADR-006) — one fewer moving part than a split-service topology.

Two things worth calling out for operators:
- **pgvector:** Dokploy's one-click Postgres service defaults to stock Postgres. The Compose file must point the Postgres service at a pgvector-enabled image (e.g. `pgvector/pgvector:pg16`) rather than relying on Dokploy's default — a configuration choice at deploy time, not a blocker.
- **Scaling beyond one node:** Dokploy supports Docker Swarm for multi-server deployments, so an operator who outgrows a single node can scale `worker` replicas (and, later, `app` replicas) via Swarm without adopting Kubernetes — the natural next step up from the `docker-compose scale`-style single-node scaling this architecture already assumed.

Raw `docker-compose up` (without Dokploy) remains a supported fallback for operators who prefer to manage their own reverse proxy and TLS — the Compose file itself has no Dokploy-specific dependency, so nothing is lost by not using it.

### 8.2 Cloud (Kubernetes / managed)
Same container image for both roles, deployed as two independently scalable Deployments — `app` (scaled by request/streaming load) and `worker` (scaled by queue depth) — differing only in the container command, plus managed PostgreSQL/Redis/S3 in place of the self-hosted stack's bundled equivalents. No image or code difference between self-hosted and cloud, and no image difference between `app` and `worker` roles either — only the entrypoint command and the orchestration around it, per `SOUL.md` §4.26.

### 8.3 CI/CD
GitHub Actions pipeline: lint → test (unit + integration) → build **one** container image → (for cloud) deploy to staging (both `app` and `worker` roles from that same image) → manual promotion to production. Self-hosted users consume tagged releases directly; there is no separate "enterprise build," and no second image to build and version alongside the first.

---

## 9. Observability Architecture

Every Model Router call and every Tool invocation emits a structured log event (correlation ID tying it to a Task/Workflow/Chat message) to a central log store, regardless of whether it originated in the ASGI process or a Celery worker. Cost and usage are aggregated from these events, not tracked separately — this guarantees the cost dashboard and the audit log can never drift out of sync with each other, since they're two views over the same event stream.

---

## 10. Scaling Considerations (forward-looking, not MVP-blocking)

- **AI modules → separate service:** the primary lever if this topology is ever outgrown. Because the Core↔AI boundary is already a documented interface (`API.md` §12) with no cross-imports that bypass it, extracting the AI modules into their own deployed service later means standing up that interface as real HTTP endpoints and pointing the existing calls at a URL instead of a Python import — a deployment and interface-transport change, not a business-logic rewrite. This is the direct payoff of ADR-006's approach versus a true single-file monolith with no internal boundary at all.
- **pgvector → dedicated vector DB:** if embedding volume/query latency outgrows pgvector, the Memory/Knowledge modules' data-access layer is written against an internal repository interface, not raw SQL scattered through the codebase — swapping the backing store is a repository-implementation change.
- **Celery → alternative queue:** the Task/Workflow execution logic is written against an internal queue-abstraction interface for the same reason.
- **Application read replicas:** standard Postgres read-replica scaling as organization/marketplace read traffic grows, with no architectural change required (Django's ORM supports replica routing natively).
- **Worker horizontal scaling:** stateless by design (all state lives in Postgres/Redis), so scaling is purely a matter of adding worker replicas — already the one axis this architecture scales independently from day one.

---

## 11. Architecture Decision Records (initial set)

| ID | Status | Decision | Rationale | Alternatives rejected |
|---|---|---|---|---|
| ADR-001 | **Superseded by ADR-006** | ~~Split Core Application (Django) and AI Services Layer (FastAPI) into two services from day one~~ | AI workloads (async, streaming, Python-ecosystem-dependent) have different scaling/reliability profiles than core CRUD; separating early avoids a painful mid-flight extraction later | Single Django monolith with async views (rejected at the time: Django's async story is second-class vs. FastAPI for streaming-heavy workloads; would also couple AI-layer deploy cadence to core app deploy cadence) — see ADR-006 for why the "separate service" conclusion itself was reconsidered, not this rejection |
| ADR-002 | Active | pgvector instead of a dedicated vector database for MVP | Avoids operating a second stateful system before scale demands it; keeps self-hosted deployment simple (one database to back up, one to reason about) | Dedicated vector DB (Pinecone/Weaviate/Qdrant) (deferred, not rejected — revisit per §10 scaling triggers) |
| ADR-003 | Active | All DeepSeek API access routes through the Model Router; no direct SDK calls from any other module | Structural enforcement of principle 7, "built on open models, deployment-agnostic" ([SOUL.md §3](SOUL.md#3-product-principles)) — a convention alone is not trustworthy enough for a core product guarantee, and it's what makes the planned self-hosted DeepSeek adapter (ADR-007) a contained addition rather than a codebase-wide hunt for direct API calls | Allowing direct DeepSeek calls "for advanced skills" (rejected: creates an unaudited backdoor around cost tracking, capability negotiation, and fallback logic) |
| ADR-004 | Active | Tauri over Electron for the Desktop Companion | Smaller binary, Rust-backed permission boundary between native capability and the web-rendered UI, better fit for a security-sensitive local-access surface | Electron (kept as documented fallback per [SOUL.md §18](SOUL.md#18-recommended-technology-stack) if a specific capability proves impractical in Tauri's webview model) |
| ADR-005 | Active | Approval gates implemented as a first-class Task/Workflow step type, not an inline conditional | Makes every approval point uniformly logged, resumable, and visible in the same status lifecycle as any other step — rather than being a special case each Tool implements differently | Per-tool custom approval UI/logic (rejected: inconsistent audit trail, harder to guarantee org-level policy floors per [SOUL.md §15.2](SOUL.md#152-the-permission--approval-system)) |
| ADR-006 | Active | Ship as a modular monolith — Django + a FastAPI ASGI sub-app mounted in the same process, one deployable image — with separate Celery worker processes, deferring the Core/AI service split until scale demands it | Operating two independently-deployed HTTP services from day one adds real operational cost (two images, two deploy pipelines, a network hop for every internal call) that isn't earned before there's real load to justify it — especially for the self-hosted single-node target audience `SOUL.md` §4.26 and §1.6 (local-first, progressive disclosure) both point toward. The Core/AI module boundary is preserved in code organization (separate Django apps and FastAPI routers, a documented interface with no bypassing cross-imports — `API.md` §12), so extraction later is a deployment and transport change, not a rewrite. The process boundary that actually matters most for responsiveness — synchronous request handling vs. background execution — was never in question and stays separate (Celery workers) from day one regardless of this decision. | Two separately-deployed services from day one (ADR-001, superseded — correctly identified a real future scaling axis, but paid that operational cost before it was needed); a true undifferentiated monolith with no internal module boundary at all (rejected: would make a future split, if ever needed, a genuine rewrite rather than a transport change) |
| ADR-007 | Active — narrows original scope | Narrow the platform from a multi-vendor Model Router (OpenAI/Anthropic/DeepSeek/Gemini/Ollama/LM Studio) to a DeepSeek-exclusive Model Router, with DeepSeek's Cloud API as the only active adapter for MVP and self-hosted DeepSeek open-weight inference as a planned second adapter (`SOUL.md` §16.2) | Product-scope decision, not a technical one: the platform's differentiation comes from being built specifically on an open-weight model family end to end (open platform + open model), not from abstracting across closed vendors. A single-adapter Router is also simply less to build and secure for MVP. The adapter-contract discipline from the original design (ADR-003) is kept even with one adapter, specifically so the planned self-hosted DeepSeek adapter is a contained addition later, not a redesign. | Keeping the full multi-vendor adapter set (rejected: builds and maintains five provider integrations for a product that no longer needs vendor choice as a feature, at the cost of MVP speed); dropping the adapter abstraction entirely and calling DeepSeek's SDK directly from application code (rejected: loses the single choke point for cost tracking, sandbox-safe tool-calling normalization, and the future cloud-vs-self-hosted swap that principle 7 depends on) |
| ADR-008 | Active | Adopt Dokploy as the recommended self-hosted deployment mechanism, deploying the same `docker-compose.yml` from §8.1 rather than a bespoke deployment tool | Dokploy is purpose-built for exactly this shape of stack (app + worker + Postgres + Redis + object storage, one compose file) and ships Traefik + Let's Encrypt TLS out of the box, removing a manual reverse-proxy configuration step for self-hosting operators without deep infra expertise — directly serving `SOUL.md` §1.6's "local-first"/self-hosted-first commitment. It also supports Docker Swarm for operators who outgrow one node, without forcing a jump to Kubernetes. | A bespoke install script driving raw `docker-compose` (rejected: reinvents TLS/reverse-proxy setup that Dokploy already solves, and gives operators no UI for logs/redeploys/rollbacks); Coolify or a similar alternative PaaS (not rejected on technical grounds — Dokploy was the operator's explicit choice); requiring Kubernetes even for single-node self-hosting (rejected: far too much operational overhead for the target self-hosting audience) |

---

*Downstream documents: `DATABASE.md` details the schema referenced here; `API.md` details the internal module interface and external API contracts described here; `SECURITY.md` expands §7; `UI_GUIDELINES.md` covers the web/desktop clients that sit above the API Gateway in §2.*
