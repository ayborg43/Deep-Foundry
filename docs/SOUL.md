## SOUL.md

# Deep-Foundry

### An Open Source AI Operating System for Intelligent Co-Workers

**Status:** Foundational document — source of truth
**Version:** 0.2.0 (Phase 1 — MVP implementation)
**Last updated:** 2026-07-12

> This document is the permanent constitution of Deep-Foundry. Every feature, architecture decision, database schema, API surface, UI pattern, and workflow must trace back to a principle or concept defined here. If a proposed change contradicts this document, the change must either be rejected or this document must be explicitly revised first — never silently overridden. All other documents (`ARCHITECTURE.md`, `ROADMAP.md`, `DATABASE.md`, `API.md`, `UI_GUIDELINES.md`, `SECURITY.md`, `CONTRIBUTING.md`) are downstream of this one.

---

## Table of Contents

1. [Product Vision](#1-product-vision)
2. [Product Goals](#2-product-goals)
3. [Product Principles](#3-product-principles)
4. [Core Concepts](#4-core-concepts)
5. [Product Modules](#5-product-modules)
6. [Complete Feature Inventory](#6-complete-feature-inventory)
7. [AI Assistant Features](#7-ai-assistant-features)
8. [Coworker Features](#8-coworker-features)
9. [Agent Teams](#9-agent-teams)
10. [Skills Marketplace](#10-skills-marketplace)
11. [Capability Packs](#11-capability-packs)
12. [Memory System](#12-memory-system)
13. [Workflow Engine](#13-workflow-engine)
14. [Desktop Companion](#14-desktop-companion)
15. [Security](#15-security)
16. [Model Router](#16-model-router)
17. [Technical Architecture](#17-technical-architecture)
18. [Recommended Technology Stack](#18-recommended-technology-stack)
19. [Roadmap](#19-roadmap)
20. [Development Rules](#20-development-rules)

---

## 1. Product Vision

### 1.1 Why this product exists

Every AI chat product today ships the same primitive: a stateless conversation window. You open a tab, type a prompt, get a response, and the moment you close the tab, the relationship resets. This is a chat interface pretending to be a productivity tool. It optimizes for "answer this one question well," not for "get real, ongoing work done alongside something that remembers, improves, and takes initiative."

Meanwhile the actual promise of large language models — reasoning, planning, tool use, autonomous execution — has outgrown the chat box. People don't want a smarter autocomplete. They want a co-worker: something with a name, a role, a memory of yesterday's decisions, permission to act inside defined boundaries, and the ability to get better at working with *them* specifically over time.

The current AI tooling landscape is also closed by default. The major assistant products are tied to proprietary, closed-weight models — you can talk to them, but you can never run them yourself, inspect them, or take them with you if the vendor changes terms, raises prices, or shuts the product down. Open source alternatives exist but are either single-agent chat clones or developer-only frameworks with no product surface a non-engineer could use, and almost none of them are built on a model family a user could actually self-host.

Deep-Foundry exists to close that gap: an **open source AI operating system built specifically on DeepSeek's model family** — open-weight, competitively priced, and credible for serious reasoning and coding work — on top of which anyone can hire, configure, and run a roster of persistent AI co-workers, give them tools and knowledge, let them work solo or in teams, and own every byte of the resulting memory and workflow data. Building on an open-weight model family, rather than a closed one, means the platform's foundation is consistent with its own open-source-first principle: today Deep-Foundry calls DeepSeek's cloud API, and the same model family is designed to be run fully self-hosted the moment that path is built out (see `SOUL.md` §16.2) — no re-platforming required to get there.

### 1.2 What problem it solves

| Problem today | Deep-Foundry's answer |
|---|---|
| AI conversations are stateless and disposable | Persistent coworkers with durable memory across sessions |
| Closed-weight models mean you can never actually own your AI stack, only rent access to it | Built on DeepSeek's open-weight model family — cloud-hosted today, self-hostable by design, so "owning your stack" is a real, reachable state rather than a marketing phrase |
| "Agents" are a developer-only concept (LangChain, raw API calls) | A product-grade UI for creating, configuring, and running agents with zero code |
| Automation requires dangerous, unsupervised agent execution | Human-in-the-loop approval gates on any consequential action |
| Every team rebuilds the same prompts, skills, and workflows from scratch | A forkable, versioned marketplace of skills, capability packs, and workflows |
| AI tools can't see your local files, terminal, or browser | An optional Desktop Companion with sandboxed, permissioned local access |
| Self-hosting AI infrastructure is either impossible or a security nightmare | A self-hosted deployment path with the same security model as the cloud offering |

### 1.3 Long-term vision

Deep-Foundry becomes the default place people go to build and run an AI workforce on open models — the way WordPress became the default place to run a website, or GitHub the default place to host code. Not a single product with a single opinion, but an **operating system**: a kernel (model router, memory, permissions, task engine) plus an ecosystem (marketplace, SDK, capability packs) that others build on top of.

In its mature form:

- A solo founder assembles a five-person AI team (research, marketing, support, ops, dev) in an afternoon, using capability packs built by the community.
- A university lab forks a "Research Coworker" pack, attaches its own paper corpus as a knowledge base, and publishes the fork back to the marketplace.
- An enterprise self-hosts the entire stack behind its firewall, running DeepSeek's open-weight models on its own infrastructure, and never sends a token to any third party.
- A developer builds and sells a niche skill (e.g., "SEC 10-K analyzer") on the marketplace, versioned and reviewed like an npm package.

### 1.4 Mission

**Give every person and every organization an extensible, trustworthy AI workforce, built on open models, that they fully own and can run entirely on their own infrastructure — not one they rent indefinitely from a closed vendor.**

### 1.5 Core philosophy

1. **Coworkers, not chatbots.** The unit of interaction is a persistent entity with a role and memory, not a conversation thread.
2. **Composable by default.** Skills, tools, knowledge, and workflows are independent, attachable units — never hardcoded into a single monolithic agent.
3. **Trust is earned through visibility, not assumed.** Every autonomous action is logged, explainable, and — where consequential — gated behind human approval.
4. **The platform is a kernel, not a cage.** Deep-Foundry's job is to provide primitives (memory, permissions, routing, orchestration) and get out of the way of what people build on top.
5. **No second-class self-hosted mode.** Whatever ships in the cloud product ships in the self-hosted product, on the same release cadence, under the same license terms for the core.

### 1.6 Design principles

- **Progressive disclosure.** A first-time user can talk to one coworker in under sixty seconds. Multi-agent teams, custom skills, and workflow automation are discoverable, not mandatory.
- **Reversibility over restriction.** Prefer undo, versioning, and audit trails over hard blocks — except where an action is irreversible or dangerous, where approval gates apply.
- **Explicit over implicit.** A coworker's permissions, attached knowledge, and model are always visible and editable, never opaque.
- **Boring technology at the core, exciting experience at the edges.** The orchestration layer (queues, databases, auth) uses proven, dull technology. The user-facing experience is where the ambition lives.

---

## 2. Product Goals

### 2.1 Short-term goals (0–6 months / MVP)

- Ship a single-user, self-hostable core: create a coworker, chat with it, attach a knowledge base, run it against DeepSeek's cloud API with reliable tool-calling.
- Ship the Model Router as the single call path to DeepSeek (chat + reasoning models, e.g. DeepSeek-V3 and DeepSeek-R1), architected so a self-hosted DeepSeek inference adapter can be added later without touching calling code (`SOUL.md` §16.2).
- Ship a useful built-in Tool set (web search, file read/write, code execution); private Skill authoring remains V2 with the Developer SDK.
- Ship a working Memory system (per-coworker + per-user, vector-search backed).
- Ship non-bypassable human-approval gates for every `dangerous` tool call, with `sensitive` actions configurable between automatic and approval-required under an organization strictness floor.
- Validate the "coworker" mental model with real users (target: 50 self-hosted installs or design-partner teams providing structured feedback).

### 2.2 Medium-term goals (6–18 months / V2)

- Launch the public Skills & Capability Pack Marketplace (browse, install, fork, rate).
- Ship Agent Teams: multi-coworker collaboration with a manager/delegation pattern.
- Ship the Workflow Engine with triggers (scheduled, event-based, manual) and human checkpoints.
- Ship Organizations & Teams: shared coworkers, shared knowledge, role-based permissions.
- Ship the Desktop Companion (local file access, terminal, browser automation, clipboard, folder watching) with a robust permission model.
- Ship a public Developer SDK so third parties can build skills, tools, and capability packs without forking the core.
- Reach marketplace liquidity: a non-trivial share of installed skills/packs are third-party, not first-party.

### 2.3 Long-term goals (18+ months / V3 and beyond)

- Multi-modal coworkers (voice, vision, video understanding) as first-class, not bolted on.
- Enterprise features: SSO/SAML, advanced audit, data residency controls, fine-grained org policy engine.
- A thriving paid-skills economy on the marketplace with revenue share for creators.
- Cross-organization coworker sharing / "coworker export-import" as a portable artifact (a coworker + its skills + its workflow templates, minus private memory, as a shareable bundle).
- Research frontier: coworkers that propose their own skill gaps ("I don't have a tool for X, should I request one?") subject to human approval before any capability is added.

### 2.4 Success metrics

| Metric | What it tells us |
|---|---|
| Weekly Active Coworkers (WAC) | Are coworkers actually being *used*, not just created once |
| Coworker retention (still active 30/60/90 days post-creation) | Is the persistent-memory value prop real |
| % of tool calls that pass through approval gates without abandonment | Is the trust/friction balance right |
| Marketplace installs per active workspace | Is the ecosystem loop working |
| Self-hosted install count + community PR velocity | Is the open-source flywheel spinning |
| Cloud-to-self-hosted-inference conversion rate (once self-hosted DeepSeek inference ships) | Is "own your stack, not rent it" actually being exercised, not just theoretically possible |
| Time from signup to first successful coworker task completion | Is onboarding delivering the "coworker, not chatbot" feeling fast enough |

---

## 3. Product Principles

These are load-bearing and should be cited by name in design reviews and PR descriptions when relevant.

1. **AI should feel like coworkers, not chatbots.** Every coworker has a name, role, avatar, and memory that persists whether or not a human is present.
2. **Human approval before dangerous actions.** Financial transactions, external communications (sending an email, posting publicly), destructive file operations, and any action tagged `irreversible` require an explicit human approval step by default.
3. **Everything should be reusable.** Skills, workflows, knowledge templates, and capability packs are first-class, shareable objects — never buried inside a single coworker's private configuration.
4. **Everything should be versioned.** Coworker configurations, skills, workflows, and capability packs carry version history with diffing and rollback.
5. **Everything should be forkable.** Any shared or marketplace object can be duplicated into a user's own workspace and modified without affecting the original or requiring permission from the original author.
6. **Community first.** Design decisions favor what strengthens the open ecosystem (marketplace, SDK, self-hosting) over what maximizes short-term platform lock-in.
7. **Built on open models, deployment-agnostic.** Deep-Foundry is built specifically on DeepSeek's model family, not a generic multi-vendor abstraction — but no feature may be built in a way that only works with DeepSeek's *cloud* service specifically. The Model Router's job is to make cloud-hosted and (once built) self-hosted DeepSeek inference interchangeable from the calling code's perspective, so choosing where the model runs is a deployment decision, not a re-architecture.
8. **Open source first.** The core platform (coworkers, memory, model router, workflow engine, permissions) is open source. Commercial offerings (hosted cloud, enterprise features, managed marketplace payments) are additive layers, never forks that withhold core capability.
9. **Privacy first.** User and organization data — memory, conversation history, knowledge bases — is never used to train shared models without explicit, revocable, opt-in consent. Data belongs to the workspace that created it.
10. **Local-first where possible.** Local model execution (self-hosted DeepSeek inference, once built — see `SOUL.md` §16.2) and local data storage are supported as first-class deployment targets, not afterthoughts bolted onto a cloud-only architecture.

---

## 4. Core Concepts

This section defines the vocabulary of the product. Every later document must use these terms consistently.

### 4.1 AI Assistant
The default, single-purpose conversational entity every user gets on signup — general-purpose, with access to the user's personal memory and any tools the user has personally authorized. The Assistant is effectively "Coworker #0": it uses the same underlying primitives as any other coworker but ships pre-configured with a broad, general-purpose role. Users graduate from "talking to the Assistant" to "assembling coworkers" as their needs specialize.

### 4.2 AI Coworkers
The central unit of the product. A Coworker is a **persistent, named, configured agent** composed of:
- A role and goal definition (system instructions, in product terms: "job description")
- A model binding (which DeepSeek model — e.g. DeepSeek-V3 for general work, DeepSeek-R1 for deep reasoning — with fallback across DeepSeek's own model tiers, via the Model Router)
- Attached Skills (reusable capability bundles)
- Attached Tools (individual callable capabilities)
- Attached Knowledge Bases
- A Memory store (private to that coworker, plus read access to shared workspace/org memory per permission)
- A Permission profile (what it's allowed to do autonomously vs. what requires approval)
- An execution mode: interactive (chat-driven) and/or background (scheduled/triggered)

Coworkers persist independent of any single conversation. Closing a chat window does not reset or destroy the coworker.

### 4.3 Agent Teams
A named, saved grouping of two or more Coworkers configured to collaborate on shared objectives, with a defined collaboration pattern (see [Section 9](#9-agent-teams)): a Manager coworker that delegates and routes tasks, specialist coworkers that execute, and optional reviewer/approval roles. Teams are themselves versionable, forkable objects.

### 4.4 Projects
A scoped container of work — conversations, tasks, attached knowledge, and assigned coworkers/teams — bounded around a goal (e.g., "Q3 Marketing Launch," "Migrate billing to Stripe"). Projects give conversations and tasks a home broader than a single chat thread but narrower than the whole workspace.

### 4.5 Workspaces
The top-level tenant boundary. A Workspace belongs to an individual user or an Organization and contains Projects, Coworkers, Teams, Knowledge Bases, and Marketplace installs. Billing, model provider credentials, and top-level permissions are scoped at the Workspace level.

### 4.6 Skills
A reusable, versioned, installable bundle of **instructions + tool bindings + optional example knowledge** that gives a coworker a specific capability (e.g., "Deep Web Research," "SQL Query Writer," "Meeting Note Summarizer"). Skills are the atomic unit of the Marketplace. A coworker can have many skills; a skill can be attached to many coworkers.

### 4.7 Tools
A single callable capability with a defined input/output schema — e.g., `web_search`, `send_email`, `run_terminal_command`, `read_file`, `query_database`. Tools are lower-level than Skills; a Skill is typically composed of one or more Tools plus the instructions for using them well. Tools carry their own permission classification (safe / sensitive / dangerous).

### 4.8 Knowledge Bases
A structured or unstructured corpus (documents, URLs, spreadsheets, databases, prior conversations) that has been ingested, chunked, embedded, and made searchable. Knowledge Bases can be scoped to a Coworker, a Project, or a Workspace, and attached to any coworker with read permission.

### 4.9 Memory
The system that lets a coworker remember facts, preferences, and history across sessions, distinct from Knowledge Bases (which are reference material, not experiential memory). See [Section 12](#12-memory-system) for full detail on memory scopes and lifecycle.

### 4.10 Workflows
A reusable, versioned, multi-step automation — a sequence of coworker/tool actions with optional conditionals, triggers, and human checkpoints. A Workflow is to a business process what a Skill is to a single capability. See [Section 13](#13-workflow-engine).

### 4.11 Tasks
A discrete unit of work assigned to a coworker or team, with a status lifecycle (`pending → in_progress → blocked/needs_approval → completed/failed`), optional due date, and audit trail. Tasks are the execution record; Workflows are the reusable template that can spawn Tasks.

### 4.12 Capability Packs
A curated bundle of pre-configured Coworkers + Skills + Knowledge templates + recommended Workflows for a specific domain or role (e.g., "Django Developer," "SEO Specialist"). Installing a Capability Pack is the fastest path from zero to a working team. See [Section 11](#11-capability-packs).

### 4.13 Marketplace
The public (and optionally private/org-internal) catalog where Skills, Capability Packs, Workflows, and Tools are published, discovered, installed, forked, rated, and reviewed. See [Section 10](#10-skills-marketplace).

### 4.14 Extensions
Third-party additions that extend the platform's own surface area — new UI panels, new integrations, new coworker capabilities — installed at the workspace level, distinct from Skills (which extend a coworker's capability set) in that Extensions can touch platform chrome, not just agent behavior.

### 4.15 Plugins
The packaging/runtime mechanism underlying both Skills and Extensions: a versioned, sandboxed unit of code + manifest that declares its required permissions, dependencies, and entry points. "Plugin" is the technical/SDK term; "Skill" and "Extension" are the product-facing terms for the two plugin categories end users interact with.

### 4.16 Desktop Companion
An optional, locally installed native application that grants coworkers permissioned access to local resources unavailable to a pure web app: the file system, clipboard, terminal, local process automation, and browser automation. See [Section 14](#14-desktop-companion).

### 4.17 Terminal Integration
A specific capability (delivered via the Desktop Companion or a sandboxed cloud shell) letting a coworker propose and, with permission, execute shell commands — always logged, always diffable, always revocable before execution for anything destructive.

### 4.18 Browser Automation
A capability letting a coworker drive a real or headless browser session (navigate, click, fill forms, read page content) for tasks that require interacting with the live web beyond simple search/fetch — gated by the same sensitive-action approval system as other Tools.

### 4.19 API Integration
The mechanism by which coworkers connect to external SaaS/services (Gmail, Slack, GitHub, Stripe, Notion, etc.) via OAuth or API keys, exposed to coworkers as Tools with scoped, revocable credentials stored in the Secrets system.

### 4.20 Notifications
Cross-channel alerts (in-app, email, push, desktop) triggered by coworker events: task completion, approval requests, workflow failures, mentions in shared projects.

### 4.21 Background Jobs
Asynchronous, non-interactive execution of coworker tasks and workflows — the mechanism that lets a coworker "work while you're away," distinct from the synchronous chat execution path. Powered by the Task Engine and a durable job queue.

### 4.22 Permissions
The system governing what a coworker, skill, tool, or workflow is allowed to do without human intervention, and what requires approval. Permissions apply at multiple layers: platform (what any coworker can ever do), workspace (org policy), coworker (individual configuration), and per-execution (one-time elevated approval). See [Section 15](#15-security).

### 4.23 Organizations
A multi-user Workspace variant with membership, roles, shared billing, and org-wide policy controls (e.g., "no coworker in this org may send external email without approval, ever — not configurable per-coworker").

### 4.24 Teams
Within an Organization, a sub-grouping of human members (not to be confused with Agent Teams) with shared access to a subset of Projects, Coworkers, and Knowledge Bases — mirrors how departments work inside a real company.

### 4.25 Billing
Usage-based and/or seat-based billing for the hosted cloud offering: model token consumption (pass-through or marked-up, transparently disclosed), marketplace revenue share, and platform subscription tiers. Self-hosted deployments bring their own model provider billing and owe Deep-Foundry nothing unless they opt into paid marketplace content or managed hosting.

### 4.26 Cloud vs. Self-hosted
Deep-Foundry ships as:
- **Self-hosted (core, open source):** Deployable via Dokploy (recommended, Docker Compose-based) or Kubernetes, full feature parity with cloud minus managed billing and managed marketplace payment processing, bring your own DeepSeek API key (or, once built, self-hosted DeepSeek inference — `SOUL.md` §16.2).
- **Cloud (hosted, commercial):** Managed infrastructure, optional managed billing for model usage, managed marketplace with payment processing, SSO/enterprise add-ons. Built on the same open source core with no forked feature set.

---

## 5. Product Modules

Each module is a bounded context with its own data ownership, though modules communicate through well-defined internal APIs (see `ARCHITECTURE.md` and `API.md` for contracts).

### 5.1 Authentication
- **Purpose:** Establish and verify identity for users and, transitively, workspaces/organizations.
- **Responsibilities:** Email/password, OAuth (Google, GitHub, Microsoft), SSO/SAML (enterprise), session management, MFA, API token issuance for the Developer SDK.
- **Dependencies:** None (foundational).
- **Future expansion:** Passkeys/WebAuthn, SCIM provisioning for enterprise, "Sign in with Vercel"-style third-party OAuth provider role (Deep-Foundry as an identity provider for its own ecosystem apps).

### 5.2 Workspace
- **Purpose:** Tenant boundary and top-level resource container.
- **Responsibilities:** Workspace creation/settings, member invitation (for orgs), billing scope, provider credential storage, workspace-level policy defaults.
- **Dependencies:** Authentication.
- **Future expansion:** Cross-workspace resource sharing (e.g., a consultant operating across multiple client workspaces with scoped access), workspace templates.

### 5.3 Coworkers
- **Purpose:** Define, configure, and manage the lifecycle of persistent AI agents.
- **Responsibilities:** Coworker CRUD, configuration versioning, skill/tool/knowledge attachment, permission profile management, performance analytics.
- **Dependencies:** Model Router, Memory, Permissions, Skills, Knowledge Bases.
- **Future expansion:** Coworker export/import as portable bundles, coworker templates authored by the community, coworker "training" via structured feedback loops.

### 5.4 Chat
- **Purpose:** The primary synchronous interaction surface between a human and one or more coworkers.
- **Responsibilities:** Message threading, streaming responses, tool-call rendering and approval prompts inline, multi-coworker (@mention) conversations, message editing/regeneration, conversation-to-memory promotion.
- **Dependencies:** Coworkers, Model Router, Memory, Permissions, Task Engine (for handoff to background execution).
- **Future expansion:** Real-time collaborative chat (multiple humans + coworkers in one thread), threaded side-conversations.

### 5.5 Voice
- **Purpose:** Spoken interaction with coworkers.
- **Responsibilities:** Speech-to-text input, text-to-speech output, voice activity detection, latency-optimized streaming pipeline, per-coworker voice persona.
- **Dependencies:** Chat, Model Router (multi-modal-capable providers).
- **Future expansion:** Real-time voice-to-voice (no intermediate text round-trip) once provider support matures; phone-line integration for coworkers as call agents.

### 5.6 Memory
- **Purpose:** Durable, queryable recall across sessions.
- **Responsibilities:** Memory write/read/edit/delete, semantic (vector) search, memory scoping and permissions, memory timeline/audit, decay/archival policy.
- **Dependencies:** Vector DB, Workspace, Coworkers.
- **Future expansion:** Automatic memory summarization/compaction, cross-coworker shared memory negotiation, memory conflict resolution when two sources disagree.

### 5.7 Marketplace
- **Purpose:** Discovery, distribution, and monetization of Skills, Capability Packs, Workflows, and Tools.
- **Responsibilities:** Listing management, versioning, install/fork mechanics, ratings/reviews, paid-listing checkout, creator payouts, security review pipeline for submissions.
- **Dependencies:** Skills, Billing, Authentication.
- **Future expansion:** Marketplace analytics dashboard for creators, private org-internal marketplaces, automated security/quality scoring for listings.

### 5.8 Admin
- **Purpose:** Workspace/organization-level administration and oversight.
- **Responsibilities:** Member/role management, policy configuration, audit log access, usage/billing dashboards, coworker/skill approval workflows for orgs that require pre-vetting.
- **Dependencies:** Workspace, Authentication, Security/Audit.
- **Future expansion:** Delegated admin roles, compliance export tooling (SOC 2 evidence bundles, etc.).

### 5.9 Projects
- **Purpose:** Scope work into goal-bound containers.
- **Responsibilities:** Project CRUD, resource association (conversations, tasks, knowledge, coworkers/teams), project-level activity feed.
- **Dependencies:** Workspace, Coworkers, Tasks.
- **Future expansion:** Project templates (paired with Capability Packs), cross-project reporting.

### 5.10 Settings
- **Purpose:** User- and workspace-level configuration surface.
- **Responsibilities:** Personal preferences, notification settings, provider API key management, default model selection, theming.
- **Dependencies:** Authentication, Workspace, Model Router.
- **Future expansion:** Granular per-coworker override settings, org-wide setting inheritance rules.

### 5.11 Desktop App
- **Purpose:** Native companion for local-machine capabilities.
- **Responsibilities:** File system access, terminal execution, clipboard bridging, folder watching, local screenshot/vision capture, offline queuing.
- **Dependencies:** Coworkers, Permissions, API Gateway (for sync back to cloud/self-hosted server).
- **Future expansion:** Full offline mode with local model fallback, cross-device companion sync.

### 5.12 Developer SDK
- **Purpose:** Enable third parties to build Skills, Tools, Extensions, and Capability Packs without forking the core.
- **Responsibilities:** SDK libraries (TypeScript/Python), local dev/test harness for skills, manifest schema and validation, publishing CLI.
- **Dependencies:** API Gateway, Marketplace.
- **Future expansion:** Visual (no-code) skill builder on top of the same SDK primitives.

### 5.13 API Gateway
- **Purpose:** Single, versioned entry point for all client (web, desktop, third-party) traffic into backend services.
- **Responsibilities:** Request routing, auth verification, rate limiting, request/response versioning, webhook ingress for external integrations.
- **Dependencies:** Authentication.
- **Future expansion:** GraphQL surface alongside REST, public API tiering for high-volume third-party integrators.

### 5.14 Model Router
- **Purpose:** The single internal interface every module uses to call DeepSeek — no application code ever calls the DeepSeek SDK/API directly. Abstracts *how* DeepSeek is reached (cloud API today, self-hosted inference once built), not *which* vendor is reached.
- **Responsibilities:** DeepSeek model capability negotiation (tool-calling, context length, reasoning vs. general-purpose model selection), fallback/retry logic (e.g. escalate from DeepSeek-V3 to DeepSeek-R1 on a reasoning-heavy request, or retry on rate limit), cost/usage tracking per call, prompt-format normalization.
- **Dependencies:** Workspace (for the DeepSeek API credential).
- **Future expansion:** A self-hosted DeepSeek inference adapter (vLLM/Ollama-style local serving of DeepSeek's open weights, per §16.2), automatic model selection based on task type/cost/latency tradeoffs, fine-tuned/custom DeepSeek model registration.
- See [Section 16](#16-model-router) for full detail.

### 5.15 Task Engine
- **Purpose:** Execute discrete units of coworker work, synchronously or asynchronously.
- **Responsibilities:** Task queuing, retry/backoff, status tracking, approval-gate insertion, result delivery back to Chat/Projects/Notifications.
- **Dependencies:** Coworkers, Permissions, Model Router, Notifications.
- **Future expansion:** Task priority scheduling, cost-budget-aware execution limits per task.

### 5.16 Workflow Engine
- **Purpose:** Orchestrate multi-step, reusable automations across coworkers and tools.
- **Responsibilities:** Workflow definition storage/versioning, trigger evaluation (scheduled/event/manual), step execution via the Task Engine, human checkpoint insertion, workflow run history.
- **Dependencies:** Task Engine, Coworkers, Marketplace (for shared workflow templates).
- **Future expansion:** Visual workflow builder, conditional branching on coworker-evaluated criteria, cross-workspace workflow sharing (enterprise).
- See [Section 13](#13-workflow-engine).

### 5.17 Observability
- **Purpose:** Give both platform operators and end users visibility into what coworkers are doing and why.
- **Responsibilities:** Structured logging of every tool call/model call, cost dashboards, coworker performance analytics, error tracking, audit trail for compliance.
- **Dependencies:** All execution-producing modules (Chat, Task Engine, Workflow Engine, Model Router).
- **Future expansion:** Anomaly detection ("this coworker's behavior changed after a skill update"), user-facing "why did you do that" explainability traces.

### 5.18 Security & Permissions
- **Purpose:** Enforce the trust boundary around autonomous action.
- **Responsibilities:** RBAC, permission policy evaluation, approval workflow UI/backend, secrets management, sandboxing for tool execution.
- **Dependencies:** Authentication, Workspace.
- **Future expansion:** Policy-as-code for enterprise org admins, fine-grained per-tool risk scoring maintained by the security team and community.
- See [Section 15](#15-security).

---

## 6. Complete Feature Inventory

Legend: **MVP** = Phase 1 build · **V2** = post-MVP expansion · **V3** = enterprise/ecosystem maturity · **Future** = directionally planned, not scheduled · **Research** = exploratory, may not ship.

### 6.1 Identity, Workspace & Admin

| Feature | Priority |
|---|---|
| Email/password + OAuth login | MVP |
| Single-user workspace | MVP |
| Personal API key/model provider management | MVP |
| Organization workspaces with member invites | V2 |
| Role-based access control (Owner/Admin/Member/Guest) | V2 |
| SSO/SAML | V3 |
| SCIM provisioning | V3 |
| Delegated admin roles | V3 |
| Compliance evidence export | V3 |
| Passkeys/WebAuthn | Future |

### 6.2 Coworkers

| Feature | Priority |
|---|---|
| Create/edit/delete coworker | MVP |
| Role/goal/personality configuration | MVP |
| Model binding per coworker | MVP |
| Skill/tool/knowledge attachment | MVP |
| Basic permission profile (autonomous vs. approval-required) | MVP |
| Coworker versioning + rollback | V2 |
| Performance analytics dashboard per coworker | V2 |
| Scheduled/background execution | V2 |
| Shared org coworkers | V2 |
| Coworker export/import bundles | V3 |
| Coworker templates marketplace | V3 |
| Self-proposed skill gap requests | V4 |

### 6.3 Chat & Interaction

| Feature | Priority |
|---|---|
| 1:1 chat with a coworker | MVP |
| Streaming responses | MVP |
| Tool-call transparency (show what the coworker is doing) | MVP |
| Inline approval prompts | MVP |
| Multi-coworker @mention in one thread | V2 |
| Conversation search | V2 |
| Message editing/regeneration/branching | V2 |
| Voice input/output | V2 |
| Real-time multi-human collaborative chat | V3 |
| Video understanding in chat | V3 |
| Real-time voice-to-voice | V4 |

### 6.4 Memory & Knowledge

| Feature | Priority |
|---|---|
| Per-coworker memory store | MVP |
| Vector semantic search over memory | MVP |
| Manual memory add/edit/delete | MVP |
| Document upload → knowledge base ingestion | MVP |
| Memory timeline/audit view | V2 |
| Project- and workspace-scoped knowledge bases | V2 |
| Spreadsheet/structured-data knowledge ingestion | V2 |
| URL/web-page knowledge ingestion with re-crawl | V2 |
| Automatic memory summarization/compaction | V3 |
| Cross-coworker shared memory negotiation | V3 |
| Memory conflict resolution | V4 |

### 6.5 Agent Teams & Workflows

| Feature | Priority |
|---|---|
| Manual sequential multi-coworker task handoff | MVP |
| Saved Agent Team definitions | V2 |
| Manager/delegator coworker pattern | V2 |
| Workflow Engine (manual trigger) | V2 |
| Scheduled workflow triggers | V2 |
| Event-based workflow triggers | V2 |
| Human checkpoints mid-workflow | V2 |
| Workflow template marketplace | V2 |
| Visual workflow builder | V3 |
| Conditional branching on coworker judgment | V3 |
| Voting/consensus among coworkers | V4 |

### 6.6 Skills, Tools & Marketplace

| Feature | Priority |
|---|---|
| Built-in first-party skills (web search, file read/write, code execution) | MVP |
| Local/private skill authoring | V2 |
| Tool permission classification (safe/sensitive/dangerous) | MVP |
| Public marketplace browse/install | V2 |
| Skill forking | V2 |
| Ratings and reviews | V2 |
| Skill versioning + update notifications | V2 |
| Paid skills + creator payouts | V3 |
| Skill dependency resolution | V3 |
| Automated security review pipeline for submissions | V3 |

### 6.7 Capability Packs

| Feature | Priority |
|---|---|
| First-party starter packs (e.g., Personal Assistant, Developer) | V2 |
| Pack install (coworkers + skills + knowledge templates + workflows in one action) | V2 |
| Community-published packs | V2 |
| Pack forking and customization | V2 |
| Pack version pinning | V3 |

### 6.8 Desktop Companion

| Feature | Priority |
|---|---|
| Local file read access (permissioned, per-folder) | V2 |
| Terminal command proposal + approval + execution | V2 |
| Clipboard read/write bridging | V2 |
| Folder watching for auto-triggered workflows | V2 |
| Browser automation | V2 |
| Screenshot understanding | V2 |
| Local indexing for fast file search | V3 |
| Full offline mode with local model fallback | V3 |

### 6.9 Integrations & Notifications

| Feature | Priority |
|---|---|
| Email (Gmail/Outlook) integration | V2 |
| Calendar integration | V2 |
| Slack/Discord integration | V2 |
| GitHub integration | V2 |
| In-app + email notifications | MVP |
| Push notifications (desktop/mobile) | V2 |
| Webhook-based custom integrations | V2 |
| Zapier/Make-style generic connector | V3 |

### 6.10 Billing & Monetization

| Feature | Priority |
|---|---|
| Free self-hosted tier (bring your own keys) | MVP |
| Hosted cloud usage-based billing | V2 |
| Seat-based org billing | V2 |
| Marketplace payment processing + payouts | V3 |
| Usage budgets/limits per coworker | V2 |

### 6.11 Observability & Trust

| Feature | Priority |
|---|---|
| Tool-call and model-call logging | MVP |
| Approval request queue | MVP |
| Cost dashboard per coworker/workspace | V2 |
| Audit log export | V2 |
| Anomaly detection on coworker behavior | V3 |
| Explainability traces ("why did you do that") | Research |

---

## 7. AI Assistant Features

The default general-purpose Assistant (see [4.1](#41-ai-assistant)) supports, at maturity:

- **Conversational:** Chat, voice, multi-turn context retention, custom instructions, custom personas.
- **Understanding:** Image understanding, video understanding, document analysis, spreadsheet analysis, multi-modal support broadly.
- **Producing:** Presentation generation, diagram generation, writing, summarization, translation, meeting notes, email drafting.
- **Reasoning & knowledge work:** Reasoning/extended thinking, coding, research, deep research, fact checking, citation generation, knowledge search across attached bases.
- **Planning & organization:** Task planning, calendar assistance.
- **Personalization:** Conversation memory, custom instructions, custom personas — the Assistant is itself just a Coworker with a broad default role, so all of Section 8's coworker features apply to it too.

Priority mapping: chat, custom instructions, and conversation memory are **MVP**. Image/document/spreadsheet understanding and writing/summarization/translation are **MVP–V2** (start with text, expand modality support as Model Router matures). Video understanding, presentation/diagram generation, and deep research are **V2–V3**.

---

## 8. Coworker Features

- **Identity:** Persistent coworkers with custom personalities, name, avatar, role, and goals.
- **Memory:** Coworker-scoped memory (see [Section 12](#12-memory-system)), learning preferences over time from explicit feedback (thumbs up/down, corrections) rather than silent inference alone.
- **Capability:** Knowledge attachment, skill attachment, tool attachment, multiple model support (a coworker can fall back from one model to another).
- **Operation:** Permissions profile, schedules for background execution, conversation history retained per coworker (not just per thread).
- **Visibility:** Performance analytics (tasks completed, approval-request rate, cost, error rate).
- **Sharing:** Shared coworkers (visible to a Team), organization coworkers (owned at the org level, not any one user).

Priority: identity, memory, capability attachment, conversation history, and a basic permission profile are **MVP**. Schedules/background execution, performance analytics, and shared/org coworkers are **V2**.

---

## 9. Agent Teams

Agent Teams formalize multi-coworker collaboration into named, reusable, versioned configurations.

### 9.1 Roles
A team is composed of coworkers each assigned a role from a common vocabulary the platform understands well enough to build routing UI around:

- **Manager** — receives the overall goal, decomposes it into subtasks, delegates to specialists, and synthesizes results.
- **Research agent** — gathers and verifies information.
- **Writer** — produces drafts of the deliverable.
- **Reviewer** — critiques output against a rubric before it's presented to the human.
- **Developer** — writes/edits code.
- **Tester** — verifies developer output.
- **Security reviewer** — audits code/action plans for risk.
- **Architect** — makes structural/design decisions before implementation.
- **Planner** — sequences work and dependencies.
- **Product Manager** — translates ambiguous human intent into a concrete spec for the rest of the team.

Roles are a labeling convention on top of ordinary Coworkers — any coworker can be assigned any role in a given team; roles are not a separate data type.

### 9.2 Collaboration mechanics
- **Delegation:** A Manager coworker can create Tasks assigned to other coworkers in the team, with the same Task Engine used for human-assigned tasks.
- **Task routing:** Tasks can be routed by explicit rule (role-based) or by Manager judgment.
- **Human approval:** Any team-generated action that would individually require approval still requires approval — teams do not bypass the permission system; delegation is not an escalation path.
- **Voting / conflict resolution (V3/Research):** For cases with no clear single decision-maker (e.g., two reviewer coworkers disagree), a voting mechanism or escalation-to-human pattern is available, off by default.

### 9.3 Data model implications
Agent Teams are covered in `DATABASE.md`; conceptually a Team is a named ordered/graph structure of Coworker references plus role labels plus a default collaboration pattern (sequential handoff, manager-delegate, or parallel-then-merge).

---

## 10. Skills Marketplace

### 10.1 Listing types
Open source skills, private (workspace-internal) skills, and paid skills all share one publishing pipeline; visibility (`public` / `unlisted` / `org-private`) and pricing (`free` / `paid` / `pay-what-you-want`) are independent listing attributes, not separate systems.

### 10.2 Lifecycle
Publishing → review (automated security scan + manifest validation; human review for paid/featured listings) → listed → installable → forkable → updatable. Every install pins a specific version; updates are opt-in per install with changelog surfaced before upgrade.

### 10.3 Social & trust layer
Ratings, written reviews, install counts, and a "verified publisher" badge (identity-verified, not a quality claim) give installers signal before attaching a third-party skill to a coworker with real permissions.

### 10.4 Forking
Forking copies a skill into the user's own workspace as an independent, editable object with provenance metadata (`forked_from: skill_id@version`) — no permission from the original author required for open source listings; paid listings may restrict forking of proprietary instruction content while still allowing configuration-level customization.

### 10.5 Dependencies, updates, and permissions
- **Dependencies:** A skill may declare dependencies on specific Tools existing in the platform/version, or on other Skills.
- **Updates:** Semantic versioning; breaking changes require a major version bump and explicit re-approval of any new permissions requested.
- **Permissions:** A skill's manifest declares every Tool it requires and that Tool's risk classification; installing a skill that requests sensitive/dangerous tools surfaces an explicit consent screen naming exactly what's being granted.

### 10.6 Skill SDK
Covered fully by the Developer SDK module ([5.12](#512-developer-sdk)); a skill is authored as a manifest (YAML/JSON: metadata, declared tools, permission requirements) plus instruction content (Markdown/prompt template) plus optional bundled example knowledge or few-shot data.

---

## 11. Capability Packs

A Capability Pack is the "batteries-included" install unit: a coordinated bundle of Coworkers + Skills + Knowledge Templates + Recommended Models + Workflows for a domain. Representative examples the marketplace should support (first-party or community, priority noted):

| Pack | Contents highlight | Priority |
|---|---|---|
| Personal Assistant | Assistant coworker + calendar/email skills + task planning workflow | V2 |
| Django Developer | Dev + Tester + Reviewer coworkers, terminal/file/git tools, framework-specific knowledge | V2 |
| Python Developer | Similar to above, general-purpose Python tooling | V2 |
| Next.js Developer | Frontend-focused dev team, browser automation for visual QA | V2 |
| DevOps | Infra coworker with terminal/cloud CLI tools, deployment workflows, incident runbooks | V2 |
| Data Scientist | Notebook/analysis tools, spreadsheet + database knowledge ingestion, chart generation | V2 |
| University Research | Deep research + citation skills, paper corpus knowledge base template | V2 |
| Startup Founder | PM + Marketing + Ops coworkers, pitch deck/diagram generation | V2 |
| SEO | Research + content + technical-audit coworkers | V2 |
| Marketing | Content Creator + Analytics coworkers, campaign workflow templates | V2 |
| Content Creator | Writing/image/video generation skills, publishing integrations | V2 |
| Customer Support | Support coworker with knowledge-base search, ticket integration | V2 |
| Sales | CRM integration, outreach drafting, meeting notes | V2 |
| Finance | Spreadsheet analysis, reporting workflows, strict approval defaults on any transaction tool | V3 |
| Legal | Document analysis, citation-heavy research, conservative permission defaults | V3 |
| Healthcare | Document/knowledge analysis with strict data-handling defaults; explicitly excludes clinical decision-making | Research |
| Education | Tutoring-oriented Assistant persona, curriculum knowledge templates | V3 |
| System Administrator | Terminal-heavy, infra monitoring, strict approval on destructive commands by default | V2 |

Every pack ships with a documented default Permission profile appropriate to its risk level (e.g., Finance/Legal packs default to maximally conservative approval gates), and packs are versioned as a unit even though their contents are individually versioned Skills/Workflows.

---

## 12. Memory System

### 12.1 Scopes
| Scope | Owner | Visibility |
|---|---|---|
| User Memory | The individual human user | Private to that user across all their coworkers |
| Coworker Memory | A specific coworker | Private to that coworker unless explicitly shared |
| Project Memory | A Project | Visible to all coworkers/humans with Project access |
| Organization Memory | An Organization | Visible per org policy/RBAC |
| Temporary Memory | A single session/task | Discarded after session end unless explicitly promoted |
| Long-term Memory | Any of the above, promoted | Persists indefinitely subject to retention policy |

### 12.2 Mechanics
- **Semantic search:** All memory is embedded and stored in a vector database (pgvector for MVP; see [Section 18](#18-recommended-technology-stack)) for retrieval-augmented recall, not just exact-match lookup.
- **Memory permissions:** Read/write access to each memory scope follows the same RBAC/permission system as everything else — a coworker cannot read another coworker's private memory without an explicit sharing grant.
- **Memory editing:** Humans can view, edit, and delete any memory entry attributed to them or their coworkers — memory is never a black box.
- **Memory timeline:** A chronological, filterable view of what was remembered, when, and from what source (conversation, task result, manual entry, workflow run) — this is the audit trail that makes memory trustworthy rather than spooky.
- **Temporary → long-term promotion:** Session-scoped working memory is explicitly promoted to durable memory either by coworker judgment (flagged for human confirmation) or explicit human action — memory does not silently accumulate everything said.

---

## 13. Workflow Engine

### 13.1 Definition
A Workflow is a versioned, reusable definition of an ordered (or conditionally branched) sequence of steps, where each step is a Coworker action, Tool call, or human checkpoint.

### 13.2 Triggers
- **Manual:** Human explicitly runs the workflow.
- **Scheduled:** Cron-style recurring execution.
- **Event-based:** Fired by an internal event (new document added to a knowledge base) or external webhook (new GitHub issue, new email).

### 13.3 Execution model
- **Conditional execution:** Branch on tool output or coworker judgment.
- **Human checkpoints:** A workflow step can be marked as requiring human sign-off before the next step runs — independent of, and stackable with, the underlying Tool-level approval gates.
- **Version history:** Every run is tied to the workflow version that executed it, so past runs remain interpretable even after the template changes.
- **Templates:** Workflows are publishable to the Marketplace exactly like Skills, with the same fork/version/rate mechanics.

---

## 14. Desktop Companion

A native, locally installed application (see [5.11](#511-desktop-app)) that extends coworker capability to the local machine, strictly opt-in and strictly permissioned per-folder/per-capability.

- **Access local files:** Read/write scoped to explicitly granted folders, never the full filesystem by default.
- **Folder watching:** Trigger workflows when files change in a watched folder.
- **Clipboard:** Read/write bridging between the coworker and the OS clipboard, with a visible indicator whenever a coworker reads clipboard contents.
- **Notifications:** Native OS notification delivery.
- **Terminal:** Command proposal with mandatory diff/preview before execution unless the specific command pattern has been pre-approved by the user.
- **Browser automation:** Local browser session driving for tasks requiring live web interaction beyond fetch/search.
- **Screenshot understanding:** Capture and multi-modal analysis of the local screen, always user-initiated or explicitly permissioned per workflow.
- **Local indexing:** Fast local file search to ground coworker file operations without re-scanning the filesystem each time.
- **Offline mode:** Queues actions locally and, where a local model is configured, can operate fully disconnected from any cloud service.
- **Secure permissions:** Every Desktop Companion capability is its own permission grant, individually revocable, individually audited — the Companion does not receive blanket "local machine access" as a single toggle.

---

## 15. Security

### 15.1 Foundations
- **Authentication:** See [5.1](#51-authentication).
- **Authorization:** RBAC at Workspace/Organization/Project/Coworker levels, evaluated centrally by the Security & Permissions module, never re-implemented ad hoc per feature.
- **Encrypted secrets:** All provider API keys, OAuth tokens, and integration credentials are encrypted at rest (envelope encryption) and never exposed in logs, prompts, or client-side payloads beyond what's minimally needed to make a call.

### 15.2 The permission & approval system
- **Permission system:** Every Tool carries a risk classification: `safe` (read-only, no side effects — e.g., web search), `sensitive` (side effects but reversible/low-blast-radius — e.g., writing a local draft file), `dangerous` (side effects that are irreversible, external-facing, or financial — e.g., sending an email, making a payment, deleting data, running arbitrary shell commands).
- **Approval workflows:** `dangerous` tool calls require human approval by default, always, with no per-coworker override that silently disables this — an org/user can pre-approve a *specific, narrowly scoped* recurring action (e.g., "always allow sending to this one email template") but cannot disable the approval system wholesale for a tool class.
- **Audit logs:** Every tool call, model call, approval decision, and permission change is logged immutably, queryable by workspace admins, exportable for compliance.
- **Sandboxing:** Tool execution (especially terminal/code execution) runs in isolated, resource-limited environments (containers/microVMs) with no default network egress beyond what the specific tool call requires.
- **API key management:** Users/orgs manage their own model provider keys; keys are never shared across workspaces and are rotatable/revocable without redeploying coworkers.
- **Role Based Access Control:** Standard role tiers (Owner, Admin, Member, Guest) at the org level, with resource-level overrides (e.g., a Guest can be granted access to one specific Project).
- **Organization permissions:** Org admins can set *floors* (minimum required approval strictness) that individual coworker configurations cannot loosen, ensuring org policy is a real guarantee, not a suggestion.

Full detail lives in `SECURITY.md`.

---

## 16. Model Router

### 16.1 Mandate
No application code — UI, Coworker logic, Skills, Workflows — ever calls DeepSeek's API directly. Everything routes through the Model Router's internal interface. Deep-Foundry is built specifically on DeepSeek's model family (per `SOUL.md` §3 principle 7) rather than abstracting across vendors — but the Router still exists as a hard choke point, because the thing it needs to abstract is *where DeepSeek inference runs* (cloud vs. self-hosted), not *which company made the model*. This is the architectural guarantee behind "own your stack, don't just rent it."

### 16.2 Supported deployment modes

| Mode | Status | Notes |
|---|---|---|
| DeepSeek Cloud API | **Active — MVP** | The only adapter implemented for MVP. Covers DeepSeek's hosted chat and reasoning models (e.g. DeepSeek-V3, DeepSeek-R1). |
| Self-hosted DeepSeek inference (open-weight models via a local serving runtime, e.g. vLLM or an Ollama-style loader) | **Planned — V2/Future** | Explicitly deferred, not abandoned (per the "cloud for now" scoping decision). Building the Cloud adapter against the same adapter contract as any future provider (§16.3) means adding this later is a contained addition, not a redesign — this is the concrete mechanism behind principle 7 ("deployment-agnostic") and behind `SOUL.md` §1.6's "local-first where possible." |

Unlike the platform's original multi-vendor ambition, there is currently no plan to add non-DeepSeek model providers (OpenAI, Anthropic, Gemini, etc.) — this is a deliberate product-scope decision, not a placeholder. If that scope ever changes, it would be a `SOUL.md` revision (`CONTRIBUTING.md` §5), not a quiet extension.

### 16.3 Responsibilities
- **Adapter contract:** Even with one active adapter, the Model Router keeps a normalized internal request/response schema (streaming protocol, tool-calling format) so the future self-hosted adapter is a second implementation of an existing contract, not a new one invented under time pressure.
- **Capability negotiation:** Track which DeepSeek models support tool calling, long context, reasoning mode, etc., and prevent assigning a coworker a capability its bound model can't deliver (or gracefully degrade with a clear UI signal).
- **Fallback/retry:** If a coworker's primary DeepSeek model is unavailable, rate-limited, or a reasoning-heavy request needs escalation, fall back to a configured secondary DeepSeek model, logged transparently.
- **Cost/usage tracking:** Every call's token usage and cost is recorded per coworker/workspace, enabling accurate cost dashboards.
- **Instant swapping (future):** Once the self-hosted adapter exists, switching a coworker between DeepSeek Cloud and self-hosted DeepSeek inference is a configuration change, not a re-implementation — memory, skills, and tools remain attached and functional (subject to capability negotiation).

---

## 17. Technical Architecture

*(Full detail in `ARCHITECTURE.md`; this is the summary that other documents must stay consistent with.)*

- **Frontend:** Web application (primary surface) + Desktop Companion (native, optional) sharing a common design system.
- **Backend:** A single modular monolith (auth, workspaces, coworkers, projects, marketplace, billing, model router, memory/embedding, task/workflow orchestration) — not two separately deployed services from day one. Core and AI functionality are organized into a hard internal module boundary (separate Django apps and a mounted FastAPI ASGI sub-app, no cross-imports that bypass the documented interface) so the seam is real in the code even though it isn't a network hop yet — extracting the AI layer into its own deployed service later, if load ever justifies it, is a deployment change against that existing interface, not a rewrite.
- **Workers:** Asynchronous execution (background Tasks, Workflow runs, knowledge ingestion/embedding, scheduled triggers) is the boundary that actually matters for responsiveness, and it *is* separate from day one — dedicated Celery worker processes, decoupled from the request/response cycle via queues, sharing the same codebase as the monolith (imported directly, not called over HTTP).
- **Queues:** Durable job queue backing the Task Engine and Workflow Engine.
- **Storage:** Relational database for structured/core data; object storage for uploaded files/knowledge source documents.
- **Search:** Full-text search for conversations/documents; vector search for semantic memory/knowledge retrieval.
- **Vector DB:** Powers Memory and Knowledge Base semantic search.
- **Desktop:** Native companion app communicating with the core backend over the API Gateway, with local-first queuing for offline resilience.
- **Browser:** Browser automation capability, either via the Desktop Companion locally or a sandboxed remote browser session for cloud-only deployments.
- **API Gateway:** Single versioned ingress for web, desktop, and third-party SDK traffic.
- **Deployment:** Container-based (Docker), deployed via Dokploy (a self-hosted PaaS that runs the same Docker Compose stack, with Traefik/TLS built in — `ARCHITECTURE.md` §8.1) for self-hosted single-node or Swarm use, and Kubernetes/managed infrastructure for the hosted cloud offering — one artifact, two deployment targets, no forked codepaths.

---

## 18. Recommended Technology Stack

**Frontend**
- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui

**Backend**
- Django + Django REST Framework (core modules: auth, workspaces, coworkers, marketplace, billing) — the outer application and ASGI process
- FastAPI (AI modules: model router, memory/embedding, task/workflow orchestration — Python-native for AI-ecosystem library compatibility), mounted as an ASGI sub-application inside the same Django-served process rather than deployed as a second service
- Celery (async task/workflow execution — a separate worker process from day one, importing the same codebase directly)
- Redis (queue broker + cache)
- PostgreSQL (primary relational store)
- pgvector (vector search extension on Postgres — avoids a separate vector DB operational burden for MVP; revisit a dedicated vector DB only if scale demands it)
- MinIO (S3-compatible object storage, self-hostable)

**Infrastructure**
- Docker (containerization for every service)
- GitHub Actions (CI/CD)
- Dokploy (self-hosted deployment — Docker Compose-based PaaS with built-in Traefik/Let's Encrypt TLS and Docker Swarm support for multi-node scaling; see `ARCHITECTURE.md` §8.1/ADR-008); Kubernetes or a managed container platform for the hosted cloud offering

**Future**
- Tauri (Desktop Companion — preferred over Electron for smaller binary size and a Rust-backed secure permission boundary between native capability and the web-rendered UI)
- Electron (optional fallback if a Desktop Companion capability proves impractical in Tauri's webview model)

**Stack rationale (why this combination, briefly):**
Django/DRF gives the core modules (auth, RBAC, billing, marketplace) a mature, batteries-included framework with a strong admin/ops story out of the box — appropriate for the parts of the system that are "boring CRUD with serious permission requirements." FastAPI is reserved for the AI modules specifically because the Python AI/ML ecosystem (embedding libraries, provider SDKs, LangChain-adjacent tooling if ever needed) is Python-first, and FastAPI's async performance suits the streaming, I/O-bound nature of model calls better than a synchronous Django view. Rather than standing these up as two independently deployed services from day one, the FastAPI app is mounted as an ASGI sub-application inside the same process Django serves — one image, one deploy pipeline, no network hop for internal calls — while Celery workers (importing that same codebase) provide the one process boundary that's actually earned this early: background execution decoupled from the request/response cycle. If the AI modules' load profile ever genuinely diverges enough to justify their own deployment, the module boundary preserved in code organization (see `ARCHITECTURE.md` ADR-006) makes that a deployment change, not a rewrite.

---

## 19. Roadmap

*(Full detail in `ROADMAP.md`; summary here for internal consistency.)*

- **Vision horizon:** The AI operating system every open-source-minded team or individual runs their AI workforce on, with a thriving third-party ecosystem.
- **Phase 1 (this phase):** Product architecture — SOUL.md and companion documents, no application code.
- **MVP:** Single-user core — coworkers, chat, memory, knowledge, Model Router against DeepSeek's Cloud API, basic permissions/approval gates, self-hostable.
- **Phase 2 / V2:** Marketplace, Agent Teams, Workflow Engine, Organizations, Desktop Companion, Developer SDK.
- **Phase 3 / V3:** Enterprise features (SSO, advanced audit, policy engine), paid marketplace economy, multi-modal maturity.
- **Enterprise:** Data residency, dedicated support, custom SLAs, on-prem/VPC deployment assistance.
- **Marketplace / Open Source Community:** Sustained investment in SDK ergonomics, creator revenue share, community governance for the core repository.

---

## 20. Development Rules

These rules bind every future contributor, human or AI, working on Deep-Foundry.

1. **Every feature requires documentation.** No feature merges without an update to the relevant document in this set (`SOUL.md` if conceptual, `ARCHITECTURE.md`/`DATABASE.md`/`API.md` if structural, `UI_GUIDELINES.md` if user-facing).
2. **Every API documented.** Every endpoint has a documented contract in `API.md` before or alongside implementation — never discovered after the fact from source code.
3. **Every database change documented.** Every schema migration is reflected in `DATABASE.md` in the same change set.
4. **Every architecture decision documented.** Non-trivial architecture decisions get a recorded rationale (an ADR-style entry) — not just the "what," but the "why," and the alternatives rejected.
5. **Every module tested.** No module ships without automated test coverage appropriate to its risk level — permission/security-critical paths require the highest coverage bar.
6. **Everything modular.** Skills, Tools, Workflows, and Capability Packs are built as independent, composable units per [Section 4](#4-core-concepts) — never hardcoded into a single monolithic agent or feature.
7. **Everything extensible.** New providers, new tool types, new integration targets are additions to an existing extension point, not special-cased forks of core logic.
8. **Everything versioned.** Coworkers, Skills, Workflows, Capability Packs, and this document itself carry version history.
9. **No silent contradiction of SOUL.md.** If an implementation detail would contradict a principle or concept defined here, the correct move is to stop and propose a revision to this document — not to quietly diverge in code.

---

*End of SOUL.md. Continue to `ARCHITECTURE.md`, `ROADMAP.md`, `DATABASE.md`, `API.md`, `UI_GUIDELINES.md`, `SECURITY.md`, and `CONTRIBUTING.md` for the documents this constitution governs.*
