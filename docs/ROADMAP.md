## ROADMAP.md

# Deep-Foundry — Roadmap

> Expands `SOUL.md` [Section 19](SOUL.md#19-roadmap) and [Section 2 (Product Goals)](SOUL.md#2-product-goals). Sequencing here reflects dependency order between modules (`ARCHITECTURE.md` §3) and feature priority tiers (`SOUL.md` §6), not calendar-date commitments — this is a phase plan, not a Gantt chart.

## Phase 0 — Product Architecture (this phase)

**Goal:** No code. Complete, internally consistent documentation: `SOUL.md` + `ARCHITECTURE.md` + `DATABASE.md` + `API.md` + `UI_GUIDELINES.md` + `SECURITY.md` + `CONTRIBUTING.md`, followed by a milestone/epic/story implementation plan.

**Exit criteria:** All seven documents complete; no unresolved contradiction between them; implementation plan reviewed and approved before any application code is written.

---

## Phase 1 — MVP: Single-User Core

**Implementation status:** Complete. Milestones 0–8 are implemented. Automated
tests cover the permission invariant and core product paths; the self-hosting
acceptance checklist in `SELF_HOSTING.md` is the release/operator verification
using that deployment's own DeepSeek, Google OAuth, and SMTP credentials.

**Goal:** Prove the central thesis — a persistent coworker with real memory and a working permission system — end to end, self-hostable, for a single user.

**In scope** (see `SOUL.md` §6 for full MVP feature list):
- Auth (email/password + one OAuth provider), single-user Workspace.
- Coworker CRUD, role/model/tool/knowledge configuration, versioning. Reusable
  Skills and their authoring/publishing lifecycle land with the V2 Developer SDK
  and Marketplace rather than shipping as a disconnected MVP-only format.
- Chat: streaming, inline tool-call transparency, inline approval prompts.
- Memory: per-user + per-coworker scopes, vector search, manual edit/delete, timeline.
- Knowledge Bases: document upload ingestion (chunk/embed), basic search.
- Model Router live against DeepSeek's Cloud API (DeepSeek-V3 and DeepSeek-R1) with capability negotiation and fallback between DeepSeek's own model tiers.
- Built-in first-party Tools: web search, workspace-scoped file read/write, and sandboxed code execution — enough to make a coworker useful without the Marketplace or private Skill SDK existing yet.
- Permission system: risk classification, approval gates for `dangerous` tools, audit log.
- Self-hosted deployment: Dokploy-managed Docker Compose, documented setup (`ARCHITECTURE.md` §8.1/ADR-008).

**Explicitly out of scope for MVP:** Agent Teams, Workflow Engine, Marketplace, Organizations, Desktop Companion (full), Developer SDK, voice, multi-modal beyond text+basic image understanding, self-hosted DeepSeek inference (cloud API only for now — see `SOUL.md` §16.2).

**Exit criteria:** A single user can self-host the stack, create a coworker, bind it to DeepSeek's Cloud API, have it remember facts across sessions, attach a document as knowledge, and have a `dangerous` tool call correctly blocked pending their approval — all without touching a database directly or reading source code.

---

## Phase 2 — V2: Teams, Marketplace, Automation

**Implementation status:** Complete in the repository. Organization/RBAC, Agent
Teams, durable workflows, Marketplace/Capability Packs, the scoped Developer SDK,
integrations, voice, self-hosted DeepSeek routing, subscriptions, and the
permission-gated Desktop Companion are implemented. Commercial cloud operation
still requires operator-owned infrastructure and payment-provider configuration.

**Goal:** Turn a single useful coworker into an ecosystem — teams of coworkers, a real marketplace, and automation that runs without a human driving every step.

**In scope** (see `SOUL.md` §6 V2 rows):
- Organizations: multi-user workspaces, RBAC, org policy floors, shared/org coworkers.
- Agent Teams: manager/delegate pattern, role vocabulary, task routing.
- Workflow Engine: manual/scheduled/event triggers, human checkpoints, run history.
- Marketplace: public listing, install, fork, rate/review, first-party Capability Packs (Personal Assistant already in MVP; Developer/DevOps/Marketing/etc. packs land here).
- Desktop Companion: file access, terminal, clipboard, folder watching, browser automation — full permission model per `SECURITY.md` §11.
- Developer SDK: skill authoring, local validation/test harness, publishing CLI.
- Integrations: email, calendar, Slack/Discord, GitHub, generic webhooks.
- Voice input/output for chat.
- Self-hosted DeepSeek inference: the second Model Router adapter (`SOUL.md` §16.2) — open-weight DeepSeek models served locally (vLLM/Ollama-style), making "own your stack, not rent it" (`SOUL.md` §1.4) a reachable state rather than a roadmap promise.
- Cloud hosted offering launches commercially (usage-based billing, managed infra) alongside continued self-hosted parity.

**Exit criteria:** A team can install a Capability Pack, get a working multi-coworker team running a scheduled workflow with at least one human checkpoint, and a third-party developer can publish a skill through the SDK without any core-team involvement.

---

## Phase 3 — V3: Enterprise & Ecosystem Maturity

**Implementation status:** Complete in the repository. Enterprise identity and
directory provisioning, delegated governance, anomaly detection and compliance
exports, marketplace security/dependencies/orders/payouts, portable coworkers,
conditional workflows, structured multimodal artifacts, residency/SLA controls,
and their administration UI are implemented. External identity, payment, and
regional infrastructure still require operator-owned provider configuration.

**Goal:** Make Deep-Foundry trustworthy and capable enough for regulated/enterprise use, and make the marketplace a real economy.

**In scope** (see `SOUL.md` §6 V3 rows):
- SSO/SAML, SCIM provisioning, delegated admin roles, compliance evidence export.
- Advanced audit: anomaly detection on coworker behavior, explainability traces.
- Paid marketplace economy: creator payouts, skill dependency resolution, automated security scoring.
- Coworker export/import as portable bundles; coworker template marketplace.
- Multi-modal maturity: video understanding, presentation/diagram generation, real-time voice groundwork.
- Visual workflow builder; conditional branching on coworker judgment.
- Data residency controls, dedicated enterprise support/SLAs.

**Exit criteria:** An enterprise design partner can self-host or run in a dedicated cloud environment, pass an internal security review using `SECURITY.md` as the reference document, and report that the marketplace's paid tier is generating real creator revenue.

---

## Phase 4 — Adaptive Collaboration

**Implementation status:** Complete in the repository. Capability-gap proposals,
cross-coworker memory reconciliation, durable Agent Team consensus, and continuous
browser voice sessions are implemented. Provider-native audio streaming remains
capability-dependent; the shipping path uses continuous speech recognition and
synthesis around the existing audited text/model pipeline.

**Goal:** Let coworkers identify missing capability, negotiate disagreement, and
participate in ambiguous decisions without weakening human control.

**In scope:**
- Coworker capability proposals. A proposal is inert until an Owner/Admin approves;
  approval attaches only an existing tool or workspace-installed skill.
- Live voice sessions with continuous browser recognition, spoken responses, typed
  fallback, private transcripts, and the normal tool-approval/memory/audit path.
- Explainable `subject: value` conflict detection across coworker memory, manual
  conflict reporting, and keep/merge resolution propagated to affected coworkers.
- Majority, unanimous, and confidence-weighted Agent Team consensus, implemented
  as durable coworker tasks with attributed votes and explicit deadlock state.

**Exit criteria:** A coworker can request a capability without receiving it,
an administrator can explicitly approve it, two coworker memories can be reconciled,
and a multi-member Agent Team can produce an auditable decision while a user can
hold a continuous voice session through the same trust controls as chat.

---

## Cross-Cutting Workstreams (run throughout every phase, not phase-gated)

### Research suite

**Implementation status:** Complete in the repository.

- Citation records retain source URL/title, publication and access dates, exact
  supporting passages, and PDF page/section locators. Chat answers and reports
  expose a responsive “View sources” panel.
- Durable deep-research runs plan queries, search and read diverse sources,
  compare conflicts, show checkpointed progress, warn on weak evidence, and
  export Markdown/JSON or structured CSV.
- Daily/weekly website monitors preserve bounded snapshot history, detect
  meaningful text changes, show diffs, and notify only the monitor owner.
- Responsible same-domain crawling supports robots handling, sitemap discovery,
  page/depth/time/rate limits, caching, and duplicate suppression.
- Public PDF, DOCX, CSV, JSON, text, HTML, and XHTML research retains document
  locators. JavaScript rendering is separately enabled and isolated behind a
  validating egress proxy.
- Research controls cover trusted/blocked domains, source diversity, recency,
  language, country, conflict detection, and quality warnings.

- **Documentation discipline** per `SOUL.md` §20 Development Rules — every phase's features update the relevant document(s) in the same change set, not as a follow-up.
- **Community/open-source health** — self-hosted install feedback loop, contribution velocity, SDK ergonomics feedback — tracked from Phase 1 onward even though the Marketplace itself doesn't ship until Phase 2, so the community pipeline isn't cold-started at V2 launch.
- **Security review** — `SECURITY.md` controls are not phased; every phase's new surface area (Marketplace in V2, Desktop Companion in V2, SSO in V3) gets a security review against the existing threat model before shipping, not after.

## Dependency Notes (why this order)

- Marketplace (V2) depends on Skills/Tools and the permission/consent model already existing and being stable (MVP) — publishing a marketplace before the permission system is trustworthy would undermine the platform's core promise.
- Agent Teams (V2) depend on Coworkers, Tasks, and the approval system (MVP) — a team is coworkers plus a collaboration pattern, not a new trust boundary.
- Workflow Engine (V2) depends on the Task Engine (MVP) — workflows are reusable templates that spawn tasks, not a parallel execution system.
- Desktop Companion (V2) depends on the permission/consent UI patterns established for cloud tool calls in MVP, so local-capability grants feel consistent rather than inventing a second mental model.
- Cloud commercial launch is sequenced into V2 (not MVP) deliberately — self-hosted-first validates the core product loop without billing/infra complexity competing for attention during the phase where the coworker concept itself is being proven.
